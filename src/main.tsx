import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ReceivingApp from './ReceivingApp';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ReceivingApp />
  </StrictMode>,
);
