// Configuration
const API_BASE = '';

let serviceCount = 1;

function addService() {
    const container = document.getElementById('services-container');
    const row = document.createElement('div');
    row.className = 'service-row';
    row.innerHTML = `
        <input type="text" class="service-name" placeholder="Nom du service">
        <input type="text" class="service-url-cpu" placeholder="URL CPU" value="/actuator/metrics/system.cpu.usage">
        <input type="text" class="service-url-ram" placeholder="URL RAM" value="/actuator/metrics/jvm.memory.used">
        <input type="number" class="service-tps" placeholder="TPS cible">
    `;
    container.appendChild(row);
    serviceCount++;
}

function getServices() {
    const rows = document.querySelectorAll('.service-row:not(.header-row)');
    const services = [];
    rows.forEach(row => {
        const nom = row.querySelector('.service-name')?.value?.trim();
        const urlCpu = row.querySelector('.service-url-cpu')?.value?.trim();
        const urlRam = row.querySelector('.service-url-ram')?.value?.trim();
        const tps = parseInt(row.querySelector('.service-tps')?.value) || 0;
        if (nom) {
            services.push({ nom, url_cpu: urlCpu, url_ram: urlRam, transactions: tps });
        }
    });
    return services;
}

function getCollectionParams() {
    const duration = parseInt(document.getElementById('duration').value) || 30;
    const interval = parseInt(document.getElementById('interval').value) || 5;
    const basePort = parseInt(document.getElementById('base-port').value) || 8080;
    return { duration, interval, basePort };
}

function showLog(message) {
    const logsDiv = document.getElementById('logs');
    logsDiv.textContent += message + '\n';
    logsDiv.classList.add('show');
    logsDiv.scrollTop = logsDiv.scrollHeight;
}

function showResult(message, isError = false) {
    const resultDiv = document.getElementById('resultats');
    resultDiv.textContent = message;
    resultDiv.className = 'show';
    if (isError) {
        resultDiv.classList.add('error');
    } else {
        resultDiv.classList.remove('error');
    }
}

async function startCollection() {
    const services = getServices();
    if (services.length === 0) {
        showResult('❌ Veuillez ajouter au moins un service.', true);
        return;
    }

    const { duration, interval, basePort } = getCollectionParams();

    const payload = {
        services: services,
        duration_seconds: duration,
        interval_seconds: interval,
        job_id: 'collecte_' + Date.now(),
        base_port: basePort
    };

    showLog('🚀 Démarrage de la collecte...');
    showLog(`📊 Durée: ${duration}s, Intervalle: ${interval}s`);
    showLog(`📦 Services: ${services.map(s => s.nom).join(', ')}`);
    showResult('⏳ Collecte en cours...');

    try {
        const response = await fetch('/api/v1/collect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok) {
            const msg = `✅ Collecte terminée !\nJob ID: ${data.job_id}\nServices: ${data.shape.services}\nÉchantillons: ${data.shape.samples}`;
            showResult(msg);
            showLog(`✅ Job ${data.job_id} terminé avec ${data.shape.services} services et ${data.shape.samples} échantillons.`);
            showLog('📁 Matrices sauvegardées dans data/raw/');
        } else {
            showResult(`❌ Erreur: ${data.detail || 'Erreur inconnue'}`, true);
            showLog(`❌ Erreur: ${data.detail}`);
        }
    } catch (error) {
        showResult(`❌ Erreur réseau: ${error.message}`, true);
        showLog(`❌ Erreur réseau: ${error.message}`);
    }
}