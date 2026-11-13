import { Routes, Route } from 'react-router-dom';
import Toolbar from '@/components/Shell/Toolbar';
import CreatorPage from '@/pages/CreatorPage';
import PlansPage from '@/pages/PlansPage';

export default function App() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#08080d' }}>
      <Toolbar />
      <Routes>
        <Route path="/" element={<CreatorPage />} />
        <Route path="/editor" element={<CreatorPage />} />
        <Route path="/plans" element={<PlansPage />} />
      </Routes>
    </div>
  );
}
