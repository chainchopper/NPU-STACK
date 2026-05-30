import React from 'react';

export default function CapabilityPill({ active = false, label, activeClassName = 'badge-success' }) {
    return <span className={`badge ${active ? activeClassName : ''}`}>{label}</span>;
}
