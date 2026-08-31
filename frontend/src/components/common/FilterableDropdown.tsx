import React, { useState, useRef, useEffect, useMemo } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'

interface Option {
  value: string
  label: string
}

interface FilterableDropdownProps {
  value: string
  onChange: (value: string) => void
  options: Option[]
  placeholder?: string
  className?: string
  menuWidthClassName?: string
}

export function FilterableDropdown({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  className = '',
  menuWidthClassName = 'w-full',
}: FilterableDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Find label for current value
  const selectedLabel = useMemo(() => {
    const matched = options.find((o) => o.value === value)
    return matched ? matched.label : ''
  }, [value, options])

  // Filter options based on search query
  const filteredOptions = useMemo(() => {
    if (!search.trim()) return options
    const query = search.toLowerCase()
    return options.filter((o) => o.label.toLowerCase().includes(query))
  }, [options, search])

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Auto-focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [isOpen])

  const handleSelect = (val: string) => {
    onChange(val)
    setIsOpen(false)
    setSearch('')
  }

  return (
    <div ref={containerRef} className="relative inline-block text-left w-full">
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center justify-between w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500/50 hover:bg-slate-750 transition-colors text-left ${className}`}
      >
        <span className="truncate">{selectedLabel || placeholder}</span>
        <ChevronDown className={`h-3 w-3 text-slate-400 shrink-0 ml-1.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className={`absolute left-0 mt-1 z-50 rounded-lg border border-slate-750 bg-slate-900 shadow-xl overflow-hidden flex flex-col max-h-60 ${menuWidthClassName}`}>
          {/* Search box inside dropdown */}
          <div className="relative border-b border-slate-800 p-1.5 shrink-0 bg-slate-950/40">
            <Search className="absolute left-3 top-2.5 h-3 w-3 text-slate-500" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded border border-slate-850 bg-slate-950/80 pl-7 pr-6 py-1 text-xs text-slate-200 placeholder-slate-500 focus:border-sky-600 focus:outline-none transition-colors"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-3 top-2 rounded hover:bg-slate-800 p-0.5"
              >
                <X className="h-3 w-3 text-slate-500 hover:text-slate-300" />
              </button>
            )}
          </div>

          {/* Scrollable list */}
          <div className="overflow-y-auto flex-1 py-1">
            {filteredOptions.length === 0 ? (
              <div className="py-3 px-3 text-center text-[10px] text-slate-500 italic">
                No components found
              </div>
            ) : (
              filteredOptions.map((opt) => {
                const isSelected = opt.value === value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => handleSelect(opt.value)}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors truncate ${
                      isSelected
                        ? 'bg-sky-600/20 text-sky-400 font-bold'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-slate-100'
                    }`}
                  >
                    {opt.label}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
