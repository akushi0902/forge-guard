/**
 * Layout store — manages the sidebar collapse state.
 *
 * The collapsed state is persisted to localStorage so it survives page
 * navigations and browser refreshes. Components read `isSidebarCollapsed`
 * and call `toggleSidebar` to mutate it.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface LayoutState {
  isSidebarCollapsed: boolean;
}

interface LayoutActions {
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

type LayoutStore = LayoutState & LayoutActions;

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      isSidebarCollapsed: false,

      toggleSidebar: () =>
        set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),

      setSidebarCollapsed: (collapsed: boolean) =>
        set({ isSidebarCollapsed: collapsed }),
    }),
    {
      name: 'forgeguard-layout',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ isSidebarCollapsed: state.isSidebarCollapsed }),
    },
  ),
);
