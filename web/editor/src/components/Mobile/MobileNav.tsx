import React from 'react';

interface MobileNavProps {
  activeTab: 'map' | 'timeline' | 'hotels' | 'settings';
  onTabChange: (tab: 'map' | 'timeline' | 'hotels' | 'settings') => void;
}

export const MobileNav: React.FC<MobileNavProps> = ({ activeTab, onTabChange }) => {
  const tabs = [
    { id: 'map' as const, icon: '🗺️', label: '地图' },
    { id: 'timeline' as const, icon: '📋', label: '行程' },
    { id: 'hotels' as const, icon: '🏨', label: '酒店' },
    { id: 'settings' as const, icon: '⚙️', label: '设置' },
  ];
  
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t z-50">
      <div className="flex items-center justify-around h-16">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex flex-col items-center justify-center flex-1 h-full ${
              activeTab === tab.id
                ? 'text-blue-500'
                : 'text-gray-500'
            }`}
          >
            <span className="text-xl">{tab.icon}</span>
            <span className="text-xs mt-1">{tab.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
};
