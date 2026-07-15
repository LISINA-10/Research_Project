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

// ----- AFFICHAGE DES MATRICES -----

let currentMatrixData = null;

async function viewMatrices(jobId) {
    const section = document.getElementById('matrix-section');
    const container = document.getElementById('matrix-container');

    try {
        const response = await fetch(`/api/v1/matrix/${jobId}`);
        if (!response.ok) {
            container.innerHTML = `<p style="color:red;">❌ Erreur: ${response.status}</p>`;
            section.style.display = 'block';
            return;
        }

        const data = await response.json();
        currentMatrixData = data;

        let html = `<p><strong>Job:</strong> ${data.job_id}</p>`;
        html += `<p><strong>Services:</strong> ${data.services.join(', ')}</p>`;
        html += `<p><strong>Échantillons:</strong> ${data.n_samples}</p>`;

        // Fonction pour générer un tableau
        function renderTable(title, matrix, unit) {
            if (!matrix || matrix.length === 0) return '';
            let table = `<h4>${title} (${unit})</h4>`;
            table += '<table class="matrix-table"><thead><tr><th>Service \\ Échantillon</th>';
            for (let j = 0; j < data.n_samples; j++) {
                table += `<th>t${j+1}</th>`;
            }
            table += '</tr></thead><tbody>';
            for (let i = 0; i < data.n_services; i++) {
                table += `<tr><td><strong>${data.services[i]}</strong></td>`;
                for (let j = 0; j < data.n_samples; j++) {
                    const val = matrix[i][j];
                    const display = (val === null || isNaN(val)) ? '—' : val.toFixed(3);
                    table += `<td>${display}</td>`;
                }
                table += '</tr>';
            }
            table += '</tbody></table>';
            return table;
        }

        html += renderTable('CPU', data.cpu, 'cœurs');
        html += renderTable('RAM', data.ram, 'octets');
        html += renderTable('Latence', data.lat, 'ms');
        html += renderTable('Débit', data.bw, 'octets/s');

        container.innerHTML = html;
        section.style.display = 'block';
    } catch (error) {
        container.innerHTML = `<p style="color:red;">❌ Erreur: ${error.message}</p>`;
        section.style.display = 'block';
    }
}

function downloadMatrixCSV() {
    if (!currentMatrixData) return;
    const data = currentMatrixData;
    let csv = 'Service,Échantillon,CPU,RAM,Latence,Débit\n';
    for (let i = 0; i < data.n_services; i++) {
        for (let j = 0; j < data.n_samples; j++) {
            const row = [
                data.services[i],
                j+1,
                data.cpu[i][j]?.toFixed(4) || '',
                data.ram[i][j]?.toFixed(4) || '',
                data.lat[i][j]?.toFixed(4) || '',
                data.bw[i][j]?.toFixed(4) || ''
            ];
            csv += row.join(',') + '\n';
        }
    }
    const blob = new Blob([csv], { type: 'text/csv' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `matrices_${data.job_id}.csv`;
    link.click();
}


async function displayJobs() {
    try {
        const response = await fetch('/api/v1/jobs');
        if (!response.ok) return;
        const data = await response.json();

        let html = '<h3>📋 Historique des collectes</h3>';
        if (!data.jobs || data.jobs.length === 0) {
            html += '<p>Aucune collecte effectuée.</p>';
        } else {
            html += '<table class="matrix-table">';
            html += '<thead><tr><th>Job ID</th><th>Services</th><th>Échantillons</th><th>Statut</th><th>Action</th></tr></thead>';
            html += '<tbody>';
            data.jobs.forEach(job => {
                html += `<tr>
                    <td><strong>${job.job_id}</strong></td>
                    <td>${job.services}</td>
                    <td>${job.samples}</td>
                    <td>${job.status}</td>
                    <td><button onclick="viewMatrices('${job.job_id}')" class="btn btn-secondary btn-small">Voir matrices</button></td>
                </tr>`;
            });
            html += '</tbody></table>';
        }
        document.getElementById('matrix-container').innerHTML = html;
        document.getElementById('matrix-section').style.display = 'block';
    } catch (error) {
        console.error('Erreur displayJobs:', error);
    }
}


document.addEventListener('DOMContentLoaded', function() {
    displayJobs();
});
