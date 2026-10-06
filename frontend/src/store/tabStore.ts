import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface TabBreadcrumb {
  title: string
  path: string
}

export interface WorkspaceTab {
  id: string
  title: string
  path: string
  icon?: string
  breadcrumbs: TabBreadcrumb[]
  formData?: Record<string, any>
  isClosable?: boolean
  createdAt: number
}

interface TabStoreState {
  tabs: WorkspaceTab[]
  activeTabId: string
}

interface TabStoreActions {
  openTab: (path: string, customTitle?: string, customIcon?: string) => string
  switchTab: (tabId: string) => string | null
  switchToIndex: (index: number) => string | null
  cycleTab: (direction: 'next' | 'prev') => string | null
  closeTab: (tabId: string) => string | null
  closeOtherTabs: (keepTabId: string) => void
  closeTabsToRight: (tabId: string) => void
  duplicateTab: (tabId: string) => string | null
  closeAllTabs: () => string
  updateActiveTab: (updates: Partial<WorkspaceTab>) => void
  updateTabTitle: (tabId: string, title: string) => void
  pushBreadcrumb: (breadcrumb: TabBreadcrumb) => void
  navigateBreadcrumb: (index: number) => string | null
  saveTabFormData: (tabId: string, formKey: string, data: any) => void
  getTabFormData: (tabId: string, formKey: string) => any
  clearTabsOnLogout: () => void
  syncWithRoute: (path: string, vesselName?: string) => void
}

export type TabStore = TabStoreState & TabStoreActions

export const DEFAULT_TAB_ID = 'tab-dashboard-home'

export function getRouteMetadata(path: string, vesselName?: string): { title: string; icon: string } {
  const cleanPath = path.split('?')[0].split('#')[0]

  if (cleanPath === '/' || cleanPath === '') {
    return { title: 'Dashboard', icon: 'LayoutDashboard' }
  }
  if (cleanPath === '/vessels') {
    return { title: 'Vessels', icon: 'Ship' }
  }
  if (cleanPath === '/library') {
    return { title: 'Library', icon: 'Library' }
  }
  if (cleanPath === '/standard-jobs-library') {
    return { title: 'Standard Jobs Library', icon: 'Layers' }
  }
  if (cleanPath === '/users') {
    return { title: 'Users', icon: 'Users' }
  }
  if (cleanPath === '/admin') {
    return { title: 'Admin', icon: 'Shield' }
  }

  // Vessel specific paths: /vessels/:vesselId/...
  const vesselMatch = cleanPath.match(/^\/vessels\/([^/]+)(?:\/(.*))?$/)
  if (vesselMatch) {
    const subRoute = vesselMatch[2] || ''
    const vPrefix = vesselName ? `${vesselName} - ` : ''

    if (!subRoute || subRoute === 'ingestion') {
      return { title: `${vPrefix}Ingestion`, icon: 'FolderOpen' }
    }
    if (subRoute.startsWith('manuals')) {
      return { title: `${vPrefix}Manuals`, icon: 'ClipboardList' }
    }
    if (subRoute.startsWith('components')) {
      return { title: `${vPrefix}Components`, icon: 'Wrench' }
    }
    if (subRoute.startsWith('jobs')) {
      return { title: `${vPrefix}Jobs`, icon: 'BookOpen' }
    }
    if (subRoute.startsWith('spares')) {
      return { title: `${vPrefix}Spares`, icon: 'Package' }
    }
    if (subRoute.startsWith('standard-jobs')) {
      return { title: `${vPrefix}Standard Jobs`, icon: 'ClipboardList' }
    }
    if (subRoute.startsWith('export-setup') || subRoute.startsWith('export')) {
      return { title: `${vPrefix}Export`, icon: 'Download' }
    }
    if (subRoute.startsWith('manual-preview')) {
      return { title: `${vPrefix}Manual Preview`, icon: 'BookOpen' }
    }
    return { title: `${vPrefix}Workflow`, icon: 'Ship' }
  }

  // Default fallback
  const segments = cleanPath.split('/').filter(Boolean)
  const lastSeg = segments[segments.length - 1] || 'Page'
  const title = lastSeg.charAt(0).toUpperCase() + lastSeg.slice(1).replace(/-/g, ' ')
  return { title, icon: 'LayoutDashboard' }
}

const createDefaultTab = (): WorkspaceTab => ({
  id: DEFAULT_TAB_ID,
  title: 'Dashboard',
  path: '/',
  icon: 'LayoutDashboard',
  breadcrumbs: [{ title: 'Dashboard', path: '/' }],
  isClosable: false,
  createdAt: Date.now(),
})

export const useTabStore = create<TabStore>()(
  persist(
    (set, get) => ({
      tabs: [createDefaultTab()],
      activeTabId: DEFAULT_TAB_ID,

      openTab: (path: string, customTitle?: string, customIcon?: string) => {
        const meta = getRouteMetadata(path)
        const title = customTitle || meta.title
        const icon = customIcon || meta.icon
        const newTabId = `tab-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`

        const newTab: WorkspaceTab = {
          id: newTabId,
          title,
          path,
          icon,
          breadcrumbs: [{ title, path }],
          isClosable: true,
          createdAt: Date.now(),
        }

        set((state) => ({
          tabs: [...state.tabs, newTab],
          activeTabId: newTabId,
        }))

        return newTabId
      },

      switchTab: (tabId: string) => {
        const tab = get().tabs.find((t) => t.id === tabId)
        if (tab) {
          set({ activeTabId: tabId })
          return tab.path
        }
        return null
      },

      switchToIndex: (index: number) => {
        const { tabs } = get()
        if (tabs.length === 0) return null

        // Standard browser Alt+9 behavior: switch to last tab if 9th pressed
        let targetIndex = index
        if (index === 8 && tabs.length > 9) {
          targetIndex = tabs.length - 1
        }

        if (targetIndex >= 0 && targetIndex < tabs.length) {
          const targetTab = tabs[targetIndex]
          set({ activeTabId: targetTab.id })
          return targetTab.path
        }
        return null
      },

      cycleTab: (direction: 'next' | 'prev') => {
        const { tabs, activeTabId } = get()
        if (tabs.length <= 1) return null

        const currentIdx = tabs.findIndex((t) => t.id === activeTabId)
        if (currentIdx === -1) return null

        let nextIdx: number
        if (direction === 'next') {
          nextIdx = (currentIdx + 1) % tabs.length
        } else {
          nextIdx = (currentIdx - 1 + tabs.length) % tabs.length
        }

        const nextTab = tabs[nextIdx]
        set({ activeTabId: nextTab.id })
        return nextTab.path
      },

      closeTab: (tabId: string) => {
        const state = get()
        const tabIndex = state.tabs.findIndex((t) => t.id === tabId)
        if (tabIndex === -1) return null

        // If only 1 tab left or closing default tab
        if (state.tabs.length <= 1) {
          const defaultTab = createDefaultTab()
          set({ tabs: [defaultTab], activeTabId: defaultTab.id })
          return defaultTab.path
        }

        const newTabs = state.tabs.filter((t) => t.id !== tabId)
        let newActiveId = state.activeTabId

        if (state.activeTabId === tabId) {
          // Select previous tab or next tab
          const nextIndex = Math.max(0, tabIndex - 1)
          newActiveId = newTabs[nextIndex]?.id || newTabs[0].id
        }

        const nextActiveTab = newTabs.find((t) => t.id === newActiveId) || newTabs[0]
        set({ tabs: newTabs, activeTabId: nextActiveTab.id })
        return nextActiveTab.path
      },

      closeOtherTabs: (keepTabId: string) => {
        const state = get()
        const kept = state.tabs.filter((t) => t.id === keepTabId || t.id === DEFAULT_TAB_ID)
        set({
          tabs: kept.length > 0 ? kept : [createDefaultTab()],
          activeTabId: keepTabId,
        })
      },

      closeTabsToRight: (tabId: string) => {
        const state = get()
        const tabIndex = state.tabs.findIndex((t) => t.id === tabId)
        if (tabIndex === -1) return

        const kept = state.tabs.slice(0, tabIndex + 1)
        const isCurrentActiveKept = kept.some((t) => t.id === state.activeTabId)

        set({
          tabs: kept,
          activeTabId: isCurrentActiveKept ? state.activeTabId : tabId,
        })
      },

      duplicateTab: (tabId: string) => {
        const state = get()
        const sourceTab = state.tabs.find((t) => t.id === tabId)
        if (!sourceTab) return null

        const sourceIndex = state.tabs.findIndex((t) => t.id === tabId)
        const newTabId = `tab-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`

        const newTab: WorkspaceTab = {
          ...sourceTab,
          id: newTabId,
          title: `${sourceTab.title} (Copy)`,
          isClosable: true,
          createdAt: Date.now(),
        }

        const newTabs = [...state.tabs]
        newTabs.splice(sourceIndex + 1, 0, newTab)

        set({
          tabs: newTabs,
          activeTabId: newTabId,
        })

        return newTab.path
      },

      closeAllTabs: () => {
        const defaultTab = createDefaultTab()
        set({ tabs: [defaultTab], activeTabId: defaultTab.id })
        return defaultTab.path
      },

      updateActiveTab: (updates: Partial<WorkspaceTab>) => {
        set((state) => ({
          tabs: state.tabs.map((tab) =>
            tab.id === state.activeTabId ? { ...tab, ...updates } : tab
          ),
        }))
      },

      updateTabTitle: (tabId: string, title: string) => {
        set((state) => ({
          tabs: state.tabs.map((tab) =>
            tab.id === tabId ? { ...tab, title } : tab
          ),
        }))
      },

      pushBreadcrumb: (breadcrumb: TabBreadcrumb) => {
        set((state) => ({
          tabs: state.tabs.map((tab) => {
            if (tab.id !== state.activeTabId) return tab

            const lastCrumb = tab.breadcrumbs[tab.breadcrumbs.length - 1]
            if (lastCrumb && lastCrumb.path === breadcrumb.path) {
              return tab
            }

            // Check if crumb already exists in history — if so, slice back to that point
            const existingIndex = tab.breadcrumbs.findIndex((b) => b.path === breadcrumb.path)
            let updatedCrumbs: TabBreadcrumb[]
            if (existingIndex !== -1) {
              updatedCrumbs = tab.breadcrumbs.slice(0, existingIndex + 1)
            } else {
              updatedCrumbs = [...tab.breadcrumbs, breadcrumb]
            }

            return {
              ...tab,
              breadcrumbs: updatedCrumbs,
            }
          }),
        }))
      },

      navigateBreadcrumb: (index: number) => {
        const state = get()
        const activeTab = state.tabs.find((t) => t.id === state.activeTabId)
        if (!activeTab || index < 0 || index >= activeTab.breadcrumbs.length) return null

        const targetCrumb = activeTab.breadcrumbs[index]
        const slicedCrumbs = activeTab.breadcrumbs.slice(0, index + 1)

        set({
          tabs: state.tabs.map((tab) =>
            tab.id === state.activeTabId
              ? { ...tab, path: targetCrumb.path, breadcrumbs: slicedCrumbs }
              : tab
          ),
        })

        return targetCrumb.path
      },

      saveTabFormData: (tabId: string, formKey: string, data: any) => {
        set((state) => ({
          tabs: state.tabs.map((tab) => {
            if (tab.id !== tabId) return tab
            return {
              ...tab,
              formData: {
                ...(tab.formData || {}),
                [formKey]: data,
              },
            }
          }),
        }))
      },

      getTabFormData: (tabId: string, formKey: string) => {
        const tab = get().tabs.find((t) => t.id === tabId)
        return tab?.formData?.[formKey] ?? null
      },

      clearTabsOnLogout: () => {
        const defaultTab = createDefaultTab()
        set({
          tabs: [defaultTab],
          activeTabId: defaultTab.id,
        })
        try {
          window.localStorage.removeItem('pms_workspace_tabs')
        } catch {
          // Ignore
        }
      },

      syncWithRoute: (path: string, vesselName?: string) => {
        const state = get()
        const activeTab = state.tabs.find((t) => t.id === state.activeTabId)
        if (!activeTab) return

        const meta = getRouteMetadata(path, vesselName)

        // Only update if path changed or title became more specific
        if (activeTab.path !== path || (vesselName && !activeTab.title.includes(vesselName))) {
          const newBreadcrumb: TabBreadcrumb = { title: meta.title, path }
          
          // Compute updated breadcrumbs
          const existingIndex = activeTab.breadcrumbs.findIndex((b) => b.path === path)
          let updatedCrumbs: TabBreadcrumb[]
          if (existingIndex !== -1) {
            updatedCrumbs = activeTab.breadcrumbs.slice(0, existingIndex + 1)
          } else {
            // Check if root crumb matches
            if (activeTab.breadcrumbs.length === 0) {
              updatedCrumbs = [newBreadcrumb]
            } else {
              updatedCrumbs = [...activeTab.breadcrumbs, newBreadcrumb]
            }
          }

          set({
            tabs: state.tabs.map((tab) =>
              tab.id === state.activeTabId
                ? {
                    ...tab,
                    path,
                    title: meta.title,
                    icon: meta.icon,
                    breadcrumbs: updatedCrumbs,
                  }
                : tab
            ),
          })
        }
      },
    }),
    {
      name: 'pms_workspace_tabs',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        tabs: state.tabs,
        activeTabId: state.activeTabId,
      }),
    }
  )
)
