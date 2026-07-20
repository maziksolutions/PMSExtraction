import React, { useState, useRef, useEffect, useMemo } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'

export interface SelectOption {
  label: string
  value: string
}

interface SearchableSelectProps {
  value: string
  onChange: (val: string) => void
  options: (string | SelectOption)[]
  placeholder?: string
  className?: string
  disabled?: boolean
  required?: boolean
  allowCustom?: boolean
}

export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  className = '',
  disabled = false,
  required = false,
  allowCustom = true,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  // Normalize options to { label, value } objects
  const normalizedOptions = useMemo<SelectOption[]>(() => {
    return options.map((opt) => (typeof opt === 'string' ? { label: opt, value: opt } : opt))
  }, [options])

  // Filter options based on search query
  const filteredOptions = useMemo(() => {
    if (!search.trim()) return normalizedOptions
    const q = search.toLowerCase()
    return normalizedOptions.filter(
      (opt) => opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q)
    )
  }, [normalizedOptions, search])

  // Handle outside click to close dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Selected option label
  const selectedOption = normalizedOptions.find((opt) => opt.value === value)
  const displayLabel = selectedOption ? selectedOption.label : value

  return (
    <div ref={containerRef} className={`relative inline-block w-full ${className}`}>
      <div
        onClick={() => {
          if (!disabled) {
            setIsOpen((prev) => !prev)
            setSearch('')
          }
        }}
        className={`flex items-center justify-between rounded-lg border px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors ${
          disabled
            ? 'border-slate-800 bg-slate-900 text-slate-500 cursor-not-allowed'
            : isOpen
            ? 'border-sky-500 bg-slate-800 text-white shadow-sm'
            : 'border-slate-700 bg-slate-800 text-slate-200 hover:border-slate-600'
        } ${required && !value ? 'border-amber-600/60' : ''}`}
      >
        <span className="truncate pr-2">
          {displayLabel ? displayLabel : <span className="text-slate-500">{placeholder}</span>}
        </span>
        <div className="flex items-center gap-1 shrink-0 text-slate-400">
          {value && !disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onChange('')
                setSearch('')
              }}
              className="hover:text-white p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          )}
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-180 text-sky-400' : ''}`} />
        </div>
      </div>

      {isOpen && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
          <div className="relative mb-1.5">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                if (allowCustom) onChange(e.target.value)
              }}
              placeholder="Search or type..."
              className="w-full rounded-lg border border-slate-700 bg-slate-800 py-1.5 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              autoFocus
            />
          </div>

          <div className="max-h-52 overflow-y-auto space-y-0.5 custom-scrollbar">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-2 text-xs text-slate-500 text-center">
                {allowCustom && search.trim() ? (
                  <span>Using custom value: &quot;<strong className="text-sky-300">{search}</strong>&quot;</span>
                ) : (
                  'No matching options'
                )}
              </div>
            ) : (
              filteredOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    onChange(opt.value)
                    setIsOpen(false)
                  }}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                    opt.value === value
                      ? 'bg-sky-600/30 text-sky-200 font-semibold'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {opt.value === value && <span className="text-[10px] text-sky-400 font-mono">Selected</span>}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
