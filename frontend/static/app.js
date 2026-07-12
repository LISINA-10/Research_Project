const API_BASE = '';

function addService() {
    const container = document.getElementById('services-container');
    const row = document.createElement('div');
    row.className = 'service-row';
    row.innerHTML = `
        <input type="text" class="service-name" placeholder="Nom du service">
        <input type="text" class="service-url-cpu" placeholder="URL CPU" value="/actuator/metrics/system.cpu.usage">
        <input type="text" class="service-url-ram" placeholder="URL RAM" value="/actuator/metrics/jvm.memory.used">
        <input type="text" class="service-url-lat" placeholder="URL Latence" value="/actuator/health">
        <input type="text" class="service-url-bw" placeholder="URL Débit" value="/actuator/health">
        <input type="number" class="service-tps" placeholder="TPS cible" value="10" min="0">
    `;
    container.appendChild(row);
}

function getServices() {
    const rows = document.querySelectorAll('.service-row:not(.header-row)');
    const services = [];

    rows.forEach(row => {
        const nom = row.querySelector('.service-name')?.value?.trim();
        const urlCpu = row.querySelector('.service-url-cpu')?.value?.trim();
        const urlRam = row.querySelector('.service-url-ram')?.value?.trim();
        const urlLat = row.querySelector('.service-url-lat')?.value?.trim() || '/actuator/health';
        const urlBw = row.querySelector('.service-url-bw')?.value?.trim() || '/actuator/health';
        const tps = parseInt(row.querySelector('.service-tps')?.value, 10) || 0;

        if (nom) {
            services.push({
                nom,
                url_cpu: urlCpu,
                url_ram: urlRam,
                url_lat: urlLat,
                url_bw: urlBw,
                transactions: tps
            });
        }
    });

    return services;
}

function getCollectionParams() {
    const duration = parseInt(document.getElementById('duration').value, 10) || 30;
    const interval = parseInt(document.getElementById('interval').value, 10) || 5;
    const basePort = parseInt(document.getElementById('base-port').value, 10) || 8080;
    return { duration, interval, basePort };
}

function showLog(message) {
    const logsDiv = document.getElementById('logs');
    logsDiv.textContent += `${message}\n`;
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

async function runCollect(payload) {
    showLog('Demarrage de la collecte...');
    showResult('Collecte en cours...');

    try {
        const response = await fetch('/api/v1/collect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok) {
            const loadInfo = data.load_enabled ? '\nCharge activee: oui' : '\nCharge activee: non';
            const msg = `Collecte terminee.\nJob ID: ${data.job_id}\nServices: ${data.shape.services}\nEchantillons: ${data.shape.samples}${loadInfo}`;
            showResult(msg);
            showLog(`Job ${data.job_id} termine (${data.shape.services} services, ${data.shape.samples} echantillons).`);
            showLog('Matrices sauvegardees dans data/raw/');
        } else {
            const detail = data.detail || 'Erreur inconnue';
            showResult(`Erreur: ${detail}`, true);
            showLog(`Erreur: ${detail}`);
        }
    } catch (error) {
        showResult(`Erreur reseau: ${error.message}`, true);
        showLog(`Erreur reseau: ${error.message}`);
    }
}

async function startCollection() {
    const services = getServices();
    if (services.length === 0) {
        showResult('Veuillez ajouter au moins un service.', true);
        return;
    }

    const { duration, interval, basePort } = getCollectionParams();
    const payload = {
        services,
        duration_seconds: duration,
        interval_seconds: interval,
        job_id: `collecte_${Date.now()}`,
        base_port: basePort
    };

    showLog(`Duree: ${duration}s, Intervalle: ${interval}s, Port: ${basePort}`);
    showLog(`Services: ${services.map(s => s.nom).join(', ')}`);
    await runCollect(payload);
}

async function startFromConfig() {
    const { duration, interval, basePort } = getCollectionParams();
    const payload = {
        use_config: true,
        duration_seconds: duration,
        interval_seconds: interval,
        job_id: `config_${Date.now()}`,
        base_port: basePort
    };

    showLog('Collecte depuis config.json');
    await runCollect(payload);
}
