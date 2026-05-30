import React from 'react';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';

const toneStyles = {
    info: {
        icon: Info,
        borderColor: 'rgba(59, 130, 246, 0.35)',
        background: 'rgba(59, 130, 246, 0.08)',
        iconColor: 'var(--accent-blue)',
        titleColor: 'var(--text-primary)',
    },
    success: {
        icon: CheckCircle2,
        borderColor: 'rgba(16, 185, 129, 0.35)',
        background: 'rgba(16, 185, 129, 0.08)',
        iconColor: 'var(--accent-green)',
        titleColor: 'var(--text-primary)',
    },
    warning: {
        icon: AlertTriangle,
        borderColor: 'rgba(245, 158, 11, 0.35)',
        background: 'rgba(245, 158, 11, 0.08)',
        iconColor: 'var(--accent-amber)',
        titleColor: 'var(--text-primary)',
    },
    danger: {
        icon: XCircle,
        borderColor: 'rgba(239, 68, 68, 0.35)',
        background: 'rgba(239, 68, 68, 0.08)',
        iconColor: 'var(--accent-red)',
        titleColor: 'var(--text-primary)',
    },
};

export default function OperationNotice({
    tone = 'info',
    title,
    message,
    details,
    footer,
    style,
}) {
    if (!title && !message && !details && !footer) {
        return null;
    }

    const palette = toneStyles[tone] || toneStyles.info;
    const Icon = palette.icon;

    return (
        <div
            role="status"
            className="card"
            style={{
                marginBottom: 16,
                borderColor: palette.borderColor,
                background: palette.background,
                ...style,
            }}
        >
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <Icon size={18} style={{ color: palette.iconColor, marginTop: 2, flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                    {title && (
                        <div style={{ fontWeight: 700, color: palette.titleColor, marginBottom: message || details || footer ? 6 : 0 }}>
                            {title}
                        </div>
                    )}
                    {message && (
                        <div style={{ color: 'var(--text-secondary)', marginBottom: details || footer ? 8 : 0 }}>
                            {message}
                        </div>
                    )}
                    {details && (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginBottom: footer ? 8 : 0 }}>
                            {details}
                        </div>
                    )}
                    {footer}
                </div>
            </div>
        </div>
    );
}
