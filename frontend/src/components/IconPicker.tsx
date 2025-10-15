"use client";

import { useState } from "react";
import {
  Wrench,
  ShoppingCart,
  RotateCcw,
  Globe,
  Info,
  Zap,
  Cloud,
  Code,
  Database,
  Mail,
  MessageSquare,
  Calendar,
  Clock,
  Settings,
  Users,
  FileText,
  Search,
  Bell,
  Lock,
  Key,
  Server,
  Cpu,
  HardDrive,
  Wifi,
  Activity,
  BarChart,
  PieChart,
  TrendingUp,
  DollarSign,
  CreditCard,
  Package,
  Truck,
  MapPin,
  Phone,
  Video,
  Camera,
  Image,
  Music,
  Film,
  BookOpen,
  Bookmark,
  Tag,
  Folder,
  Upload,
  Download,
  Share2,
  Link,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";

// Available icons mapped by name
export const AVAILABLE_ICONS: Record<string, LucideIcon> = {
  Wrench,
  ShoppingCart,
  RotateCcw,
  Globe,
  Info,
  Zap,
  Cloud,
  Code,
  Database,
  Mail,
  MessageSquare,
  Calendar,
  Clock,
  Settings,
  Users,
  FileText,
  Search,
  Bell,
  Lock,
  Key,
  Server,
  Cpu,
  HardDrive,
  Wifi,
  Activity,
  BarChart,
  PieChart,
  TrendingUp,
  DollarSign,
  CreditCard,
  Package,
  Truck,
  MapPin,
  Phone,
  Video,
  Camera,
  Image,
  Music,
  Film,
  BookOpen,
  Bookmark,
  Tag,
  Folder,
  Upload,
  Download,
  Share2,
  Link,
  ExternalLink,
};

interface IconPickerProps {
  selectedIcon: string;
  onIconSelect: (iconName: string) => void;
}

export function IconPicker({ selectedIcon, onIconSelect }: IconPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const SelectedIconComponent = AVAILABLE_ICONS[selectedIcon] || Wrench;

  const filteredIcons = Object.keys(AVAILABLE_ICONS).filter((iconName) =>
    iconName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="relative">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Icon
      </label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 w-full border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
      >
        <SelectedIconComponent className="w-5 h-5" />
        <span className="flex-1 text-left">{selectedIcon}</span>
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          {/* Dropdown */}
          <div className="absolute z-20 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md shadow-lg max-h-96 overflow-hidden">
            {/* Search */}
            <div className="p-2 border-b border-gray-200 dark:border-gray-700">
              <input
                type="text"
                placeholder="Search icons..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
            {/* Icon Grid */}
            <div className="grid grid-cols-6 gap-2 p-3 overflow-y-auto max-h-80">
              {filteredIcons.map((iconName) => {
                const IconComponent = AVAILABLE_ICONS[iconName];
                const isSelected = iconName === selectedIcon;
                return (
                  <button
                    key={iconName}
                    type="button"
                    onClick={() => {
                      onIconSelect(iconName);
                      setIsOpen(false);
                      setSearchQuery("");
                    }}
                    className={`flex flex-col items-center justify-center p-3 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${
                      isSelected
                        ? "bg-blue-100 dark:bg-blue-900/20 ring-2 ring-blue-500"
                        : ""
                    }`}
                    title={iconName}
                  >
                    <IconComponent className="w-6 h-6" />
                    <span className="text-xs mt-1 truncate w-full text-center">
                      {iconName}
                    </span>
                  </button>
                );
              })}
            </div>
            {filteredIcons.length === 0 && (
              <div className="p-4 text-center text-gray-500 dark:text-gray-400">
                No icons found
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
