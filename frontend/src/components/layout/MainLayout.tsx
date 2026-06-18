'use client';

import React, { useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";

interface MainLayoutProps {
  children: React.ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen bg-bg-primary text-text-primary overflow-hidden">
      {/* Collapsible Left Sidebar */}
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />

      {/* Main Right Area */}
      <div className={`flex-1 flex flex-col min-w-0 relative transition-all duration-300 ${
        sidebarCollapsed ? "pl-[72px]" : "pl-[260px]"
      }`}>
        {/* Top Header (includes TickerBand internally) */}
        <Header />

        {/* Scrollable Content Container */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 space-y-6">
          <div className="max-w-7xl mx-auto w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
