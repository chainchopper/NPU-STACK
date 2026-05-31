import React from 'react';
import ChatPlayground from './ChatPlayground';

export default function Chat() {
  return <ChatPlayground defaultView="chat" defaultMode="agent" defaultContext="general" />;
}
