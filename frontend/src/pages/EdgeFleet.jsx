import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Wifi, Usb, Bluetooth, Search, RefreshCw, HardDrive, Terminal,
    Download, Trash2, Edit3, Check, X, Radio, CircleDot,
    ChevronDown, ChevronUp, Zap, Server, MonitorSmartphone, Shield,
    Link2, PackageOpen, Upload,
} from 'lucide-react';
import {
    absoluteUrl,
    detectDeviceChip,
    downloadPreparedBundleUrl,
    espBackup,
    inferBackendOrigin,
    installPreparedBundle,
    listBackups,
    listDevices,
    listPreparedBundles,
    pairDevice,
    prepareDevice,
    removeDevice,
    rp2040Detect,
    scanDevices,
    unpairDevice,
    updateDevice,
} from '../api/client';

const familyColor = {
    esp32: 'blue', 'esp32-s2': 'blue', 'esp32-s3': 'amber',
    'esp32-c3': 'amber', 'esp32-c6': 'amber', 'esp32-h2': 'amber', 'esp32-p4': 'purple',
    esp8266: 'blue', rp2040: 'green', rp2350: 'green', 'rpi-sbc': 'green',
    arduino: 'blue', teensy: 'blue', stm32: 'amber', nrf: 'blue',
    'uart-bridge': 'blue', serial: 'blue', microchip: 'blue',
    rockchip: 'purple', allwinner: 'purple', qualcomm: 'purple',
    coral: 'purple', movidius: 'purple', nvidia: 'green',
    circuitpython: 'green', google: 'blue', unknown: 'blue',
};

const statusLabel = {
    detected: { text: 'Detected', cls: 'green' },
    online: { text: 'Online', cls: 'green' },
    reachable: { text: 'Reachable', cls: 'blue' },
    visible: { text: 'Visible', cls: 'blue' },
    bootsel: { text: 'BOOTSEL', cls: 'amber' },
    mounted: { text: 'Mounted', cls: 'green' },
    offline: { text: 'Offline', cls: '' },
};

const connIcon = {
    usb: Usb,
    wifi: Wifi,
    ble: Bluetooth,
    'usb-mass-storage': HardDrive,
};

function buildProvisioningDefaults() {
    return {
        wifi_ssid: '',
        wifi_password: '',
        mqtt_broker: typeof window !== 'undefined' ? window.location.hostname : '',
        command_center_url: inferBackendOrigin(),
        agent_port: 9200,
    };
}

function formatBundleDownloadUrl(bundle) {
    if (bundle?.download_url) return absoluteUrl(bundle.download_url);
    if (bundle?.bundle_id) return absoluteUrl(downloadPreparedBundleUrl(bundle.bundle_id));
    return '#';
}

export default function EdgeFleet() {
    const [devices, setDevices] = useState([]);
    const [summary, setSummary] = useState({ count: 0, paired_count: 0, detected_count: 0, available_count: 0, hidden_low_confidence: 0 });
    const [preparedBundles, setPreparedBundles] = useState([]);
    const [bundleSelectionByDevice, setBundleSelectionByDevice] = useState({});
    const [scanning, setScanning] = useState(false);
    const [scanOpts, setScanOpts] = useState({ usb: true, mdns: true, ble: false, subnet: false });
    const [filter, setFilter] = useState('all');
    const [log, setLog] = useState([]);
    const [backups, setBackups] = useState([]);
    const [expandedId, setExpandedId] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [editName, setEditName] = useState('');
    const [loading, setLoading] = useState(true);
    const [provisioningConfig, setProvisioningConfig] = useState(buildProvisioningDefaults);

    const addLog = (msg) => {
        setLog((prev) => [...prev.slice(-59), `${new Date().toLocaleTimeString()} — ${msg}`]);
    };

    const fetchDevices = useCallback(async () => {
        try {
            const data = await listDevices();
            setDevices(data.devices || []);
            setSummary({
                count: data.count || 0,
                paired_count: data.paired_count || 0,
                detected_count: data.detected_count || 0,
                available_count: data.available_count || 0,
                hidden_low_confidence: data.hidden_low_confidence || 0,
            });
        } catch {
            // Backend not available.
        }
        setLoading(false);
    }, []);

    const fetchBackups = useCallback(async () => {
        try {
            const data = await listBackups();
            setBackups(data.backups || []);
        } catch {
            // ignore
        }
    }, []);

    const fetchPreparedBundles = useCallback(async () => {
        try {
            const data = await listPreparedBundles();
            setPreparedBundles(data.bundles || []);
        } catch {
            // ignore
        }
    }, []);

    useEffect(() => {
        fetchDevices();
        fetchBackups();
        fetchPreparedBundles();
    }, [fetchBackups, fetchDevices, fetchPreparedBundles]);

    const latestBundleByDevice = useMemo(() => {
        const latest = {};
        for (const bundle of preparedBundles) {
            if (!latest[bundle.device_id]) {
                latest[bundle.device_id] = bundle;
            }
        }
        return latest;
    }, [preparedBundles]);

    const compatibleBundlesForDevice = useCallback((device) => {
        const compatibleProfileIds = new Set(
            (device?.profiles || [])
                .filter((profile) => profile.compatible)
                .map((profile) => profile.id),
        );

        if (!compatibleProfileIds.size) {
            return [];
        }

        return preparedBundles.filter((bundle) => compatibleProfileIds.has(bundle.profile_id));
    }, [preparedBundles]);

    const runScan = async () => {
        setScanning(true);
        const methods = Object.entries(scanOpts).filter(([, enabled]) => enabled).map(([key]) => key);
        addLog(`Scanning via ${methods.join(', ')}...`);
        try {
            const data = await scanDevices(scanOpts);
            setDevices(data.devices || []);
            setSummary((prev) => ({
                ...prev,
                count: data.devices?.length || prev.count,
                available_count: (data.devices || []).filter((device) => device.available).length,
                hidden_low_confidence: data.hidden_low_confidence || 0,
            }));
            addLog(`Found ${data.devices_found || 0} device(s), ${data.total_registered || 0} registered`);
        } catch (error) {
            addLog(`Scan failed: ${error.message}`);
        }
        setScanning(false);
    };

    const handleUpdate = async (id) => {
        try {
            await updateDevice(id, { nickname: editName });
            addLog(`Renamed ${id}`);
            setEditingId(null);
            fetchDevices();
        } catch {
            addLog(`Rename failed for ${id}`);
        }
    };

    const handleRemove = async (id) => {
        try {
            await removeDevice(id);
            addLog(`Removed ${id}`);
            setDevices((prev) => prev.filter((device) => device.id !== id));
        } catch {
            addLog(`Failed to remove ${id}`);
        }
    };

    const handlePairToggle = async (device) => {
        try {
            if (device.paired) {
                await unpairDevice(device.id);
                addLog(`Unpaired ${device.nickname || device.chip || device.id}`);
            } else {
                await pairDevice(device.id);
                addLog(`Paired ${device.nickname || device.chip || device.id}`);
            }
            fetchDevices();
        } catch (error) {
            addLog(`Pairing failed: ${error.message}`);
        }
    };

    const handlePrepare = async (device, profileId) => {
        const selectedProfile = profileId || device.recommended_profile;
        if (!selectedProfile) {
            addLog(`No compatible profile for ${device.id}`);
            return;
        }

        try {
            const result = await prepareDevice(device.id, {
                ...provisioningConfig,
                profile_id: selectedProfile,
                device_name: device.nickname || device.chip || device.id,
            });
            setBundleSelectionByDevice((prev) => ({ ...prev, [device.id]: result.bundle_id }));
            addLog(`Prepared ${result.profile_name} bundle for ${device.nickname || device.chip || device.id}`);
            await fetchPreparedBundles();
            await fetchDevices();
        } catch (error) {
            addLog(`Prepare failed: ${error.message}`);
        }
    };

    const handleInstallBundle = async (device, bundleId) => {
        const bundle = preparedBundles.find((entry) => entry.bundle_id === bundleId) || latestBundleByDevice[device.id];
        if (!bundle) {
            addLog(`No prepared bundle available for ${device.nickname || device.chip || device.id}`);
            return;
        }

        try {
            const result = await installPreparedBundle(device.id, bundle.bundle_id);
            if (result.status === 'manual-step-required') {
                addLog(`Install requires manual step for ${device.id}`);
            } else {
                addLog(`Installed bundle to ${device.drive || device.id}`);
            }
            await fetchDevices();
        } catch (error) {
            addLog(`Install failed: ${error.message}`);
        }
    };

    const handleEspDetect = async (device) => {
        addLog(`Detecting chip on ${device.port}...`);
        try {
            const data = await detectDeviceChip(device.id);
            if (data.error) {
                addLog(`Error: ${data.error}`);
            } else {
                const profileNote = data.recommended_profile ? ` • bundle ready: ${data.recommended_profile}` : '';
                addLog(`Chip: ${data.chip || data.family || 'detected'}${profileNote}`);
            }
            await fetchDevices();
        } catch (error) {
            addLog(`Detect failed: ${error.message}`);
        }
    };

    const handleEspBackup = async (device) => {
        addLog(`Backing up firmware from ${device.port} (may take 30-60s)...`);
        try {
            const data = await espBackup(device.port, device.flash_mb || 4);
            addLog(data.error ? `Error: ${data.error}` : `✓ Backup saved: ${data.filename}`);
            fetchBackups();
        } catch (error) {
            addLog(`Backup failed: ${error.message}`);
        }
    };

    const handleRp2040Detect = async () => {
        addLog('Scanning for RP2040 BOOTSEL drives...');
        try {
            const data = await rp2040Detect();
            if (data.count > 0 && data.devices?.length) {
                const drives = data.devices.map((device) => device.drive).filter(Boolean).join(', ');
                addLog(`Found ${data.count} BOOTSEL device(s)${drives ? ` at ${drives}` : ''}`);
            } else {
                addLog('No RP2040 in BOOTSEL mode');
            }
            fetchDevices();
        } catch (error) {
            addLog(`RP2040 detect failed: ${error.message}`);
        }
    };

    const filtered = devices.filter((device) => {
        if (filter === 'all') return true;
        if (filter === 'usb') return device.connection === 'usb' || device.connection === 'usb-mass-storage';
        if (filter === 'wifi') return device.connection === 'wifi';
        if (filter === 'ble') return device.connection === 'ble';
        if (filter === 'npu') return device.has_npu;
        if (filter === 'paired') return device.paired;
        return true;
    });

    const pairedDevices = filtered.filter((device) => device.paired);
    const detectedDevices = filtered.filter((device) => !device.paired);

    const renderDeviceCard = (device) => {
        const color = familyColor[device.family] || 'blue';
        const ConnIcon = connIcon[device.connection] || Radio;
        const state = statusLabel[device.status] || { text: device.status, cls: '' };
        const isExpanded = expandedId === device.id;
        const compatibleBundles = compatibleBundlesForDevice(device);
        const selectedBundleId = bundleSelectionByDevice[device.id] || latestBundleByDevice[device.id]?.bundle_id || compatibleBundles[0]?.bundle_id || '';
        const selectedBundle = compatibleBundles.find((bundle) => bundle.bundle_id === selectedBundleId) || latestBundleByDevice[device.id] || null;
        const family = String(device.family || '');

        return (
            <div key={device.id} className={`card fleet-device-card ${color}`}>
                <div className="fleet-device-header">
                    <div className="fleet-device-icon">
                        <ConnIcon size={20} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="fleet-device-name-row">
                            <span className={`fleet-status-dot ${state.cls}`} />
                            {editingId === device.id ? (
                                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                    <input
                                        className="input"
                                        value={editName}
                                        onChange={(event) => setEditName(event.target.value)}
                                        onKeyDown={(event) => event.key === 'Enter' && handleUpdate(device.id)}
                                        autoFocus
                                        style={{ width: 150, padding: '4px 8px', fontSize: 13 }}
                                    />
                                    <button className="fleet-icon-btn green" onClick={() => handleUpdate(device.id)}><Check size={14} /></button>
                                    <button className="fleet-icon-btn red" onClick={() => setEditingId(null)}><X size={14} /></button>
                                </div>
                            ) : (
                                <span className="fleet-device-name">
                                    {device.nickname || device.chip || device.name || device.id}
                                    <button className="fleet-edit-btn" onClick={() => { setEditingId(device.id); setEditName(device.nickname || ''); }}>
                                        <Edit3 size={12} />
                                    </button>
                                </span>
                            )}
                        </div>
                        <div className="fleet-device-badges">
                            <span className={`fleet-badge ${color}`}>{family.toUpperCase() || 'UNKNOWN'}</span>
                            {device.paired && <span className="fleet-badge purple"><Link2 size={10} /> PAIRED</span>}
                            {device.has_npu && <span className="fleet-badge purple"><Zap size={10} /> NPU</span>}
                            <span className="fleet-port">{device.port || device.drive || device.ip || device.address || ''}</span>
                        </div>
                    </div>
                    <button className="fleet-expand-btn" onClick={() => setExpandedId(isExpanded ? null : device.id)}>
                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                </div>

                {isExpanded && (
                    <div className="fleet-device-detail">
                        <div className="fleet-detail-grid">
                            {device.chip && <><span className="fleet-detail-label">Chip</span><span>{device.chip}</span></>}
                            {device.description && <><span className="fleet-detail-label">Description</span><span>{device.description}</span></>}
                            {device.manufacturer && <><span className="fleet-detail-label">Manufacturer</span><span>{device.manufacturer}</span></>}
                            {device.flash_mb > 0 && <><span className="fleet-detail-label">Flash</span><span>{device.flash_mb} MB</span></>}
                            {device.drive && <><span className="fleet-detail-label">Drive</span><span>{device.drive}</span></>}
                            {device.rssi != null && <><span className="fleet-detail-label">RSSI</span><span>{device.rssi} dBm</span></>}
                            <span className="fleet-detail-label">Connection</span><span>{device.connection}</span>
                            <span className="fleet-detail-label">Status</span><span>{state.text}</span>
                            <span className="fleet-detail-label">Paired</span><span>{device.paired ? 'Yes' : 'No'}</span>
                            <span className="fleet-detail-label">Recommended Bundle</span><span>{device.recommended_profile || '—'}</span>
                            {device.last_seen && <><span className="fleet-detail-label">Last Seen</span><span>{new Date(device.last_seen).toLocaleString()}</span></>}
                        </div>

                        {selectedBundle && (
                            <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                                Selected bundle: <strong>{selectedBundle.profile_name}</strong> • {new Date(selectedBundle.created_at).toLocaleString()}
                            </div>
                        )}

                        {compatibleBundles.length > 0 && (
                            <div style={{ marginBottom: 12 }}>
                                <label className="fleet-detail-label" style={{ display: 'block', marginBottom: 6 }}>Prepared Bundle</label>
                                <select
                                    className="input"
                                    value={selectedBundleId}
                                    onChange={(event) => setBundleSelectionByDevice((prev) => ({ ...prev, [device.id]: event.target.value }))}
                                    style={{ width: '100%' }}
                                >
                                    {compatibleBundles.map((bundle) => (
                                        <option key={bundle.bundle_id} value={bundle.bundle_id}>
                                            {bundle.profile_name} • {bundle.device_id} • {new Date(bundle.created_at).toLocaleString()}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        {selectedBundle?.instructions?.length > 0 && !device.capabilities?.install && (
                            <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                                {selectedBundle.instructions.slice(0, 3).map((line, index) => (
                                    <div key={`${selectedBundle.bundle_id}-instruction-${index}`}>{line}</div>
                                ))}
                            </div>
                        )}

                        <div className="fleet-actions">
                            <button className="btn btn-secondary" onClick={() => handlePairToggle(device)}>
                                <Link2 size={14} /> {device.paired ? 'Unpair' : 'Pair'}
                            </button>
                            {device.capabilities?.prepare && (
                                <button className="btn btn-secondary" onClick={() => handlePrepare(device)}>
                                    <PackageOpen size={14} /> Prepare Bundle
                                </button>
                            )}
                            {selectedBundle && (
                                <a className="btn btn-secondary" href={formatBundleDownloadUrl(selectedBundle)} target="_blank" rel="noreferrer">
                                    <Download size={14} /> Download Bundle
                                </a>
                            )}
                            {device.capabilities?.install && selectedBundle && (
                                <button className="btn btn-secondary" onClick={() => handleInstallBundle(device, selectedBundle.bundle_id)}>
                                    <Upload size={14} /> Install Bundle
                                </button>
                            )}
                            {device.capabilities?.chip_detect && device.connection === 'usb' && (
                                <>
                                    <button className="btn btn-secondary" onClick={() => handleEspDetect(device)}><Search size={14} /> Detect Chip</button>
                                </>
                            )}
                            {device.capabilities?.backup && device.connection === 'usb' && (
                                <button className="btn btn-secondary" onClick={() => handleEspBackup(device)}><Download size={14} /> Backup FW</button>
                            )}
                            <button className="btn btn-danger" onClick={() => handleRemove(device.id)}><Trash2 size={14} /> Remove</button>
                        </div>
                    </div>
                )}
            </div>
        );
    };

    if (loading) {
        return (
            <div className="loading-overlay">
                <div className="spinner" />
                <span>Loading fleet data...</span>
            </div>
        );
    }

    return (
        <div>
            <div className="page-header">
                <h2>Edge Device Fleet</h2>
                <p>Detect boards immediately, pair them for management, and prepare repo-native firmware bundles from the existing NPU-STACK device stack.</p>
            </div>

            <div className="metrics-grid">
                <div className="metric-card blue">
                    <div className="metric-icon"><MonitorSmartphone size={22} /></div>
                    <div className="metric-value">{summary.count || devices.length}</div>
                    <div className="metric-label">Registered Devices</div>
                </div>
                <div className="metric-card green">
                    <div className="metric-icon"><Link2 size={22} /></div>
                    <div className="metric-value">{summary.paired_count || devices.filter((device) => device.paired).length}</div>
                    <div className="metric-label">Paired Devices</div>
                </div>
                <div className="metric-card amber">
                    <div className="metric-icon"><Wifi size={22} /></div>
                    <div className="metric-value">{summary.available_count || devices.filter((device) => device.available).length}</div>
                    <div className="metric-label">Available Now</div>
                </div>
                <div className="metric-card purple">
                    <div className="metric-icon"><Shield size={22} /></div>
                    <div className="metric-value">{preparedBundles.length}</div>
                    <div className="metric-label">Prepared Bundles</div>
                </div>
            </div>

            <div className="card" style={{ marginBottom: 24 }}>
                <div className="card-header">
                    <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Search size={18} /> Discovery & Provisioning Controls
                    </div>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary" onClick={handleRp2040Detect}>
                            <HardDrive size={16} /> Detect BOOTSEL
                        </button>
                        <button className={`btn btn-primary ${scanning ? 'btn-loading' : ''}`} onClick={runScan} disabled={scanning}>
                            <RefreshCw size={16} className={scanning ? 'animate-spin' : ''} />
                            {scanning ? 'Scanning...' : 'Scan Now'}
                        </button>
                    </div>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
                    {[
                        ['usb', Usb, 'USB / Serial'],
                        ['mdns', Wifi, 'WiFi (mDNS)'],
                        ['ble', Bluetooth, 'Bluetooth LE'],
                        ['subnet', Server, 'Subnet Scan'],
                    ].map(([key, Icon, label]) => (
                        <label
                            key={key}
                            className="fleet-toggle"
                            data-active={scanOpts[key]}
                            onClick={() => setScanOpts((prev) => ({ ...prev, [key]: !prev[key] }))}
                        >
                            <Icon size={14} />
                            {label}
                        </label>
                    ))}
                </div>

                <div className="fleet-filters">
                    {['all', 'paired', 'usb', 'wifi', 'ble', 'npu'].map((value) => (
                        <button key={value} className={`fleet-filter-btn ${filter === value ? 'active' : ''}`} onClick={() => setFilter(value)}>
                            {value.toUpperCase()}
                        </button>
                    ))}
                    <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {filtered.length} shown • hidden low-confidence: {summary.hidden_low_confidence || 0}
                    </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginTop: 16 }}>
                    <input
                        className="input"
                        placeholder="Wi-Fi SSID"
                        value={provisioningConfig.wifi_ssid}
                        onChange={(event) => setProvisioningConfig((prev) => ({ ...prev, wifi_ssid: event.target.value }))}
                    />
                    <input
                        className="input"
                        type="password"
                        placeholder="Wi-Fi password"
                        value={provisioningConfig.wifi_password}
                        onChange={(event) => setProvisioningConfig((prev) => ({ ...prev, wifi_password: event.target.value }))}
                    />
                    <input
                        className="input"
                        placeholder="MQTT broker / host"
                        value={provisioningConfig.mqtt_broker}
                        onChange={(event) => setProvisioningConfig((prev) => ({ ...prev, mqtt_broker: event.target.value }))}
                    />
                    <input
                        className="input"
                        placeholder="Command center URL"
                        value={provisioningConfig.command_center_url}
                        onChange={(event) => setProvisioningConfig((prev) => ({ ...prev, command_center_url: event.target.value }))}
                    />
                </div>
                <div style={{ marginTop: 10, color: 'var(--text-muted)', fontSize: 12 }}>
                    These values are injected when you prepare device bundles for ESP32, CircuitPython, and Linux edge targets.
                </div>
            </div>

            {filtered.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '60px 20px' }}>
                    <CircleDot size={48} style={{ color: 'var(--text-muted)', margin: '0 auto 16px' }} />
                    <p style={{ color: 'var(--text-secondary)', fontSize: 15, marginBottom: 4 }}>No devices found</p>
                    <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Click “Scan Now” to discover connected hardware.</p>
                </div>
            ) : (
                <>
                    <div className="page-header" style={{ marginTop: 16 }}>
                        <h2>Paired Devices</h2>
                        <p>Devices already approved for active management and provisioning.</p>
                    </div>
                    <div className="fleet-grid">
                        {pairedDevices.length > 0 ? pairedDevices.map(renderDeviceCard) : (
                            <div className="card" style={{ gridColumn: '1 / -1', padding: 24, color: 'var(--text-muted)' }}>
                                No paired devices yet — pair a detected board to move it into managed inventory.
                            </div>
                        )}
                    </div>

                    <div className="page-header" style={{ marginTop: 24 }}>
                        <h2>Detected Devices</h2>
                        <p>Freshly discovered boards, mounts, and network nodes awaiting pairing or bundle preparation.</p>
                    </div>
                    <div className="fleet-grid">
                        {detectedDevices.length > 0 ? detectedDevices.map(renderDeviceCard) : (
                            <div className="card" style={{ gridColumn: '1 / -1', padding: 24, color: 'var(--text-muted)' }}>
                                Nothing in the detected queue for the current filter.
                            </div>
                        )}
                    </div>
                </>
            )}

            {(preparedBundles.length > 0 || backups.length > 0) && (
                <div className="metrics-grid" style={{ marginTop: 24 }}>
                    {preparedBundles.length > 0 && (
                        <div className="card" style={{ minHeight: 0 }}>
                            <div className="card-header">
                                <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <PackageOpen size={18} /> Prepared Bundles ({preparedBundles.length})
                                </div>
                            </div>
                            <div className="fleet-backup-list">
                                {preparedBundles.slice(0, 8).map((bundle) => (
                                    <div key={bundle.bundle_id} className="fleet-backup-item">
                                        <PackageOpen size={14} style={{ color: 'var(--accent-blue)' }} />
                                        <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                                            <div>
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{bundle.profile_name}</div>
                                                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{bundle.device_id}</div>
                                            </div>
                                            <a href={formatBundleDownloadUrl(bundle)} target="_blank" rel="noreferrer" className="fleet-edit-btn" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                                <Download size={12} /> ZIP
                                            </a>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {backups.length > 0 && (
                        <div className="card" style={{ minHeight: 0 }}>
                            <div className="card-header">
                                <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <HardDrive size={18} /> Firmware Backups ({backups.length})
                                </div>
                            </div>
                            <div className="fleet-backup-list">
                                {backups.slice(0, 8).map((backup) => (
                                    <div key={backup.filename} className="fleet-backup-item">
                                        <Download size={14} style={{ color: 'var(--accent-blue)' }} />
                                        <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{backup.filename}</span>
                                            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{backup.size_mb} MB</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {log.length > 0 && (
                <div className="card" style={{ marginTop: 24 }}>
                    <div className="card-header">
                        <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Terminal size={18} /> Activity Log
                        </div>
                        <button className="btn btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={() => setLog([])}>
                            Clear
                        </button>
                    </div>
                    <div className="fleet-log">
                        {log.map((line, index) => <div key={index} className="fleet-log-line">{line}</div>)}
                    </div>
                </div>
            )}
        </div>
    );
}
