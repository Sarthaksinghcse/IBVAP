import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function Layout() {
  return (
    <div className="flex min-h-screen w-full bg-[var(--bg-page)] text-[var(--text-primary)] transition-colors duration-200">
      {/* Fixed Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 min-w-0 min-h-screen">
        <TopBar />

        <main className="flex-1 p-4 lg:p-6 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
