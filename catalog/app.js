/*
 * GTA V ALLIN1 - Vehicle Catalog
 *
 * Loads vehicle data, renders a filterable grid, and exports a config.toml
 * with the user's vehicle selections.
 *
 * Vehicle data is embedded directly below. To regenerate from vehicles.toml,
 * run: allin1 export-catalog-json > catalog/vehicles.json
 * and update the VEHICLES array.
 */

// This will be populated from vehicles.toml -- for now we use a placeholder
// that gets replaced by the build script or loaded from vehicles.json.
let VEHICLES = [];

// State
const selected = new Set();

// --- DOM refs ---
const grid = document.getElementById('vehicleGrid');
const searchInput = document.getElementById('search');
const classFilter = document.getElementById('classFilter');
const mfgFilter = document.getElementById('mfgFilter');
const selectedCountEl = document.getElementById('selectedCount');
const totalCountEl = document.getElementById('totalCount');
const exportModal = document.getElementById('exportModal');
const exportOutput = document.getElementById('exportOutput');

// --- Init ---
async function init() {
    // Try loading from vehicles.json first, fall back to embedded data
    try {
        const resp = await fetch('vehicles.json');
        if (resp.ok) {
            VEHICLES = await resp.json();
        }
    } catch (e) {
        // vehicles.json not available, use embedded data
    }

    if (VEHICLES.length === 0) {
        grid.innerHTML = '<div class="empty-state">No vehicle data loaded.<br>Run <code>allin1 export-catalog</code> to generate vehicles.json</div>';
        return;
    }

    // Select all by default
    VEHICLES.forEach(v => selected.add(v.model));

    populateFilters();
    render();
    updateStats();
}

function populateFilters() {
    const classes = [...new Set(VEHICLES.map(v => v.class))].sort();
    const mfgs = [...new Set(VEHICLES.map(v => v.manufacturer))].sort();

    classes.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c.charAt(0).toUpperCase() + c.slice(1);
        classFilter.appendChild(opt);
    });

    mfgs.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        mfgFilter.appendChild(opt);
    });
}

function getFilteredVehicles() {
    const query = searchInput.value.toLowerCase().trim();
    const cls = classFilter.value;
    const mfg = mfgFilter.value;

    return VEHICLES.filter(v => {
        if (cls && v.class !== cls) return false;
        if (mfg && v.manufacturer !== mfg) return false;
        if (query) {
            const haystack = `${v.model} ${v.name} ${v.manufacturer}`.toLowerCase();
            if (!haystack.includes(query)) return false;
        }
        return true;
    });
}

function render() {
    const filtered = getFilteredVehicles();
    grid.innerHTML = '';

    if (filtered.length === 0) {
        grid.innerHTML = '<div class="empty-state">No vehicles match your filters.</div>';
        return;
    }

    // Group by class
    const grouped = {};
    filtered.forEach(v => {
        if (!grouped[v.class]) grouped[v.class] = [];
        grouped[v.class].push(v);
    });

    const sortedClasses = Object.keys(grouped).sort();

    sortedClasses.forEach(cls => {
        // Class header
        const header = document.createElement('div');
        header.className = 'class-header';

        const count = grouped[cls].length;
        const selectedInClass = grouped[cls].filter(v => selected.has(v.model)).length;

        header.innerHTML = `
            <h2>${cls} (${count})</h2>
            <div class="divider"></div>
            <div class="class-actions">
                <button class="btn" data-select-class="${cls}">Select All</button>
                <button class="btn" data-deselect-class="${cls}">Deselect</button>
            </div>
        `;
        grid.appendChild(header);

        // Vehicle cards
        grouped[cls].sort((a, b) => a.name.localeCompare(b.name));
        grouped[cls].forEach(v => {
            const card = document.createElement('div');
            card.className = `vehicle-card${selected.has(v.model) ? ' selected' : ''}`;
            card.dataset.model = v.model;

            card.innerHTML = `
                <div class="model-name">${v.model}</div>
                <div class="display-name">${v.name}</div>
                <div class="manufacturer">${v.manufacturer}</div>
                <div class="meta">
                    <span class="class-tag">${v.class}</span>
                    <span class="price">${v.price ? '$' + v.price.toLocaleString() : 'Free'}</span>
                </div>
            `;

            card.addEventListener('click', () => toggleVehicle(v.model, card));
            grid.appendChild(card);
        });
    });
}

function toggleVehicle(model, card) {
    if (selected.has(model)) {
        selected.delete(model);
        card.classList.remove('selected');
    } else {
        selected.add(model);
        card.classList.add('selected');
    }
    updateStats();
}

function updateStats() {
    selectedCountEl.textContent = selected.size;
    totalCountEl.textContent = VEHICLES.length;
}

function selectAllVisible() {
    const filtered = getFilteredVehicles();
    filtered.forEach(v => selected.add(v.model));
    render();
    updateStats();
}

function deselectAllVisible() {
    const filtered = getFilteredVehicles();
    filtered.forEach(v => selected.delete(v.model));
    render();
    updateStats();
}

function selectClass(cls) {
    VEHICLES.filter(v => v.class === cls).forEach(v => selected.add(v.model));
    render();
    updateStats();
}

function deselectClass(cls) {
    VEHICLES.filter(v => v.class === cls).forEach(v => selected.delete(v.model));
    render();
    updateStats();
}

function generateConfig() {
    const allModels = new Set(VEHICLES.map(v => v.model));
    const disabled = [...allModels].filter(m => !selected.has(m)).sort();

    let toml = '# GTA V ALLIN1 Configuration\n';
    toml += '# Generated by the ALLIN1 Vehicle Catalog\n\n';
    toml += '[general]\n';
    toml += 'gta_path = "auto"\n';
    toml += 'free_mode = false\n';
    toml += 'backup = true\n\n';
    toml += '[traffic]\n';
    toml += 'enabled = true\n';
    toml += 'density = "medium"\n';
    toml += 'rich_areas_only_supers = true\n\n';
    toml += '[vehicles]\n';

    if (disabled.length === 0) {
        toml += 'enable_all = true\n';
        toml += 'disabled_classes = []\n';
        toml += 'disabled_vehicles = []\n';
    } else if (selected.size === 0) {
        toml += 'enable_all = false\n';
        toml += 'disabled_classes = []\n';
        toml += 'disabled_vehicles = []\n';
    } else {
        toml += 'enable_all = true\n';
        toml += 'disabled_classes = []\n';

        // Check if entire classes are disabled
        const classCounts = {};
        const classDisabledCounts = {};
        VEHICLES.forEach(v => {
            classCounts[v.class] = (classCounts[v.class] || 0) + 1;
            if (!selected.has(v.model)) {
                classDisabledCounts[v.class] = (classDisabledCounts[v.class] || 0) + 1;
            }
        });

        const fullyDisabledClasses = Object.keys(classCounts).filter(
            cls => classDisabledCounts[cls] === classCounts[cls]
        );

        if (fullyDisabledClasses.length > 0) {
            toml = toml.replace(
                'disabled_classes = []',
                `disabled_classes = [${fullyDisabledClasses.map(c => `"${c}"`).join(', ')}]`
            );
        }

        // Individual disabled vehicles (excluding those in fully disabled classes)
        const individualDisabled = disabled.filter(m => {
            const v = VEHICLES.find(veh => veh.model === m);
            return v && !fullyDisabledClasses.includes(v.class);
        });

        if (individualDisabled.length > 0) {
            toml = toml.replace(
                'disabled_vehicles = []',
                `disabled_vehicles = [\n${individualDisabled.map(m => `    "${m}"`).join(',\n')}\n]`
            );
        }
    }

    return toml;
}

function showExportModal() {
    exportOutput.value = generateConfig();
    exportModal.classList.add('active');
}

function hideExportModal() {
    exportModal.classList.remove('active');
}

function copyConfig() {
    exportOutput.select();
    navigator.clipboard.writeText(exportOutput.value).then(() => {
        const btn = document.getElementById('copyBtn');
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy to Clipboard'; }, 2000);
    });
}

function downloadConfig() {
    const blob = new Blob([exportOutput.value], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'config.toml';
    a.click();
    URL.revokeObjectURL(url);
}

// --- Event listeners ---
searchInput.addEventListener('input', render);
classFilter.addEventListener('change', render);
mfgFilter.addEventListener('change', render);

document.getElementById('selectAll').addEventListener('click', selectAllVisible);
document.getElementById('deselectAll').addEventListener('click', deselectAllVisible);
document.getElementById('exportBtn').addEventListener('click', showExportModal);
document.getElementById('closeModal').addEventListener('click', hideExportModal);
document.getElementById('copyBtn').addEventListener('click', copyConfig);
document.getElementById('downloadBtn').addEventListener('click', downloadConfig);

exportModal.addEventListener('click', (e) => {
    if (e.target === exportModal) hideExportModal();
});

// Class-level select/deselect via delegated events
grid.addEventListener('click', (e) => {
    const selectBtn = e.target.closest('[data-select-class]');
    const deselectBtn = e.target.closest('[data-deselect-class]');

    if (selectBtn) {
        selectClass(selectBtn.dataset.selectClass);
    } else if (deselectBtn) {
        deselectClass(deselectBtn.dataset.deselectClass);
    }
});

// Keyboard shortcut: Escape closes modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideExportModal();
});

// Start
init();
