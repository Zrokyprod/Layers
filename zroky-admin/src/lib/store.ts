import { create } from "zustand";
import { persist } from "zustand/middleware";

interface DashboardState {
  // Sidebar state
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  closeSidebar: () => void;
  openSidebar: () => void;

  // Global filters
  selectedProject: string | null;
  setSelectedProject: (project: string | null) => void;
  dateRange: { from: Date | null; to: Date | null };
  setDateRange: (range: { from: Date | null; to: Date | null }) => void;

  // Notifications
  unreadNotifications: number;
  setUnreadNotifications: (count: number) => void;
  incrementNotifications: () => void;

  // Keyboard shortcuts
  keyboardShortcutsEnabled: boolean;
  toggleKeyboardShortcuts: () => void;

  // Real-time updates
  realTimeEnabled: boolean;
  toggleRealTime: () => void;

  // Last visited
  lastVisitedPage: string;
  setLastVisitedPage: (page: string) => void;

  // SDK connection status (set by home page SSE stream)
  sdkConnected: boolean;
  setSdkConnected: (v: boolean) => void;
  // Fixes UI state: local assignments, snoozes (client-side), and dismissed flags
  assignments: Record<string, string | null>;
  setAssignment: (diagnosisId: string, userId: string | null) => void;
  clearAssignment: (diagnosisId: string) => void;
  snoozes: Record<string, string>; // iso datetime string keyed by diagnosisId
  setSnooze: (diagnosisId: string, untilIso: string) => void;
  clearSnooze: (diagnosisId: string) => void;
  dismissed: Record<string, boolean>;
  setDismissed: (diagnosisId: string, v: boolean) => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      // Sidebar
      sidebarOpen: true,
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      closeSidebar: () => set({ sidebarOpen: false }),
      openSidebar: () => set({ sidebarOpen: true }),

      // Filters
      selectedProject: null,
      setSelectedProject: (project) => set({ selectedProject: project }),
      dateRange: { from: null, to: null },
      setDateRange: (range) => set({ dateRange: range }),

      // Notifications
      unreadNotifications: 0,
      setUnreadNotifications: (count) => set({ unreadNotifications: count }),
      incrementNotifications: () =>
        set((state) => ({ unreadNotifications: state.unreadNotifications + 1 })),

      // Keyboard shortcuts
      keyboardShortcutsEnabled: true,
      toggleKeyboardShortcuts: () =>
        set((state) => ({ keyboardShortcutsEnabled: !state.keyboardShortcutsEnabled })),

      // Real-time
      realTimeEnabled: true,
      toggleRealTime: () =>
        set((state) => ({ realTimeEnabled: !state.realTimeEnabled })),

      // Last visited
      lastVisitedPage: "/agents",
      setLastVisitedPage: (page) => set({ lastVisitedPage: page }),

      // SDK connection status
      sdkConnected: false,
      setSdkConnected: (v) => set({ sdkConnected: v }),
      // Fixes UI state
      assignments: {},
      setAssignment: (diagnosisId, userId) =>
        set((state) => ({ assignments: { ...state.assignments, [diagnosisId.toLowerCase()]: userId } })),
      clearAssignment: (diagnosisId) =>
        set((state) => {
          const copy = { ...state.assignments };
          delete copy[diagnosisId.toLowerCase()];
          return { assignments: copy };
        }),
      snoozes: {},
      setSnooze: (diagnosisId, untilIso) =>
        set((state) => ({ snoozes: { ...state.snoozes, [diagnosisId.toLowerCase()]: untilIso } })),
      clearSnooze: (diagnosisId) =>
        set((state) => {
          const copy = { ...state.snoozes };
          delete copy[diagnosisId.toLowerCase()];
          return { snoozes: copy };
        }),
      dismissed: {},
      setDismissed: (diagnosisId, v) =>
        set((state) => ({ dismissed: { ...state.dismissed, [diagnosisId.toLowerCase()]: !!v } })),
    }),
    {
      name: "dashboard-store",
      partialize: (state) => ({
        sidebarOpen: state.sidebarOpen,
        keyboardShortcutsEnabled: state.keyboardShortcutsEnabled,
        realTimeEnabled: state.realTimeEnabled,
        lastVisitedPage: state.lastVisitedPage,
        selectedProject: state.selectedProject,
        assignments: state.assignments,
        snoozes: state.snoozes,
        dismissed: state.dismissed,
      }),
    }
  )
);
