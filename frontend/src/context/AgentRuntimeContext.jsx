import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
    deleteAgentRuntime,
    discoverAgentRuntimes,
    getCurrentAgentRuntimeSelection,
    listAgentRuntimes,
    probeAgentRuntime,
    registerAgentRuntime,
    selectAgentRuntime,
    updateAgentRuntime,
} from '../api/client';

const DEFAULT_RUNTIME_ID = 'nirvana-default';
const AgentRuntimeContext = createContext(null);

function catalogFromResponse(payload) {
    return Array.isArray(payload?.runtimes) ? payload.runtimes : [];
}

function selectedIdFromResponse(payload, fallback = DEFAULT_RUNTIME_ID) {
    return payload?.selected_runtime_id || payload?.runtime?.runtime_id || fallback;
}

export function AgentRuntimeProvider({ children }) {
    const [runtimes, setRuntimes] = useState([]);
    const [selectedRuntimeId, setSelectedRuntimeId] = useState(DEFAULT_RUNTIME_ID);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const applyCatalog = useCallback((payload) => {
        const nextRuntimes = catalogFromResponse(payload);
        setRuntimes(nextRuntimes);
        setSelectedRuntimeId(selectedIdFromResponse(payload));
        return nextRuntimes;
    }, []);

    const refresh = useCallback(async ({ probe = false } = {}) => {
        setLoading(true);
        setError('');
        try {
            const [catalog, selection] = await Promise.all([
                listAgentRuntimes({ probe }),
                getCurrentAgentRuntimeSelection(),
            ]);
            const selectedId = selectedIdFromResponse(selection, selectedIdFromResponse(catalog));
            const nextRuntimes = catalogFromResponse(catalog).map((runtime) => ({
                ...runtime,
                selected: runtime.runtime_id === selectedId,
            }));
            setRuntimes(nextRuntimes);
            setSelectedRuntimeId(selectedId);
            return nextRuntimes;
        } catch (err) {
            setError(err.message || 'Unable to load agent runtimes');
            return [];
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const discover = useCallback(async ({ probe = true } = {}) => {
        setBusy(true);
        setError('');
        try {
            const payload = await discoverAgentRuntimes({ probe });
            applyCatalog(payload);
            return catalogFromResponse(payload);
        } catch (err) {
            setError(err.message || 'Runtime discovery failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, [applyCatalog]);

    const probe = useCallback(async (runtimeId) => {
        setBusy(true);
        setError('');
        try {
            const runtime = await probeAgentRuntime(runtimeId);
            setRuntimes((current) => current.map((item) => (
                item.runtime_id === runtime.runtime_id ? runtime : item
            )));
            return runtime;
        } catch (err) {
            setError(err.message || 'Runtime probe failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, []);

    const select = useCallback(async (runtimeId, allowUnready = true) => {
        setBusy(true);
        setError('');
        try {
            const payload = await selectAgentRuntime(runtimeId, allowUnready);
            const selectedId = selectedIdFromResponse(payload, runtimeId);
            setSelectedRuntimeId(selectedId);
            setRuntimes((current) => current.map((runtime) => ({
                ...runtime,
                selected: runtime.runtime_id === selectedId,
                ...(runtime.runtime_id === selectedId && payload.runtime ? payload.runtime : {}),
            })));
            return payload.runtime;
        } catch (err) {
            setError(err.message || 'Runtime selection failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, []);

    const register = useCallback(async (payload) => {
        setBusy(true);
        setError('');
        try {
            const runtime = await registerAgentRuntime(payload);
            setRuntimes((current) => [...current.filter((item) => item.runtime_id !== runtime.runtime_id), runtime]);
            return runtime;
        } catch (err) {
            setError(err.message || 'Runtime registration failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, []);

    const update = useCallback(async (runtimeId, payload) => {
        setBusy(true);
        setError('');
        try {
            const runtime = await updateAgentRuntime(runtimeId, payload);
            setRuntimes((current) => current.map((item) => (
                item.runtime_id === runtime.runtime_id ? runtime : item
            )));
            return runtime;
        } catch (err) {
            setError(err.message || 'Runtime update failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, []);

    const remove = useCallback(async (runtimeId) => {
        setBusy(true);
        setError('');
        try {
            await deleteAgentRuntime(runtimeId);
            setRuntimes((current) => current.filter((runtime) => runtime.runtime_id !== runtimeId));
            if (selectedRuntimeId === runtimeId) setSelectedRuntimeId(DEFAULT_RUNTIME_ID);
        } catch (err) {
            setError(err.message || 'Runtime removal failed');
            throw err;
        } finally {
            setBusy(false);
        }
    }, [selectedRuntimeId]);

    const selectedRuntime = useMemo(
        () => runtimes.find((runtime) => runtime.runtime_id === selectedRuntimeId) || null,
        [runtimes, selectedRuntimeId],
    );

    const value = useMemo(() => ({
        runtimes,
        selectedRuntime,
        selectedRuntimeId,
        // The default selection is implicit so old runtime_mode callers retain their behavior.
        runtimeIdForRequests: selectedRuntimeId === DEFAULT_RUNTIME_ID ? undefined : selectedRuntimeId,
        loading,
        busy,
        error,
        refresh,
        discover,
        probe,
        select,
        register,
        update,
        remove,
        clearError: () => setError(''),
    }), [busy, discover, error, loading, probe, refresh, register, remove, runtimes, select, selectedRuntime, selectedRuntimeId, update]);

    return <AgentRuntimeContext.Provider value={value}>{children}</AgentRuntimeContext.Provider>;
}

export function useAgentRuntime() {
    const context = useContext(AgentRuntimeContext);
    if (!context) throw new Error('useAgentRuntime must be used inside AgentRuntimeProvider');
    return context;
}

export { DEFAULT_RUNTIME_ID };