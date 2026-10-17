// Les icônes de l'explorateur : de petits tracés SVG en ligne, aux couleurs du texte (`currentColor`), sans dépendance.
// Décoratives : le nom accessible d'un bouton vient toujours de son texte ou de son `aria-label`.
import type {ReactNode} from 'react';

function Icon({children, size=18}:Readonly<{children:ReactNode; size?:number}>){
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{children}</svg>;
}

export const CalendarIcon=()=><Icon><rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></Icon>;
export const SearchIcon=()=><Icon><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></Icon>;
export const LayersIcon=()=><Icon><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/></Icon>;
export const GearIcon=()=><Icon><circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></Icon>;
export const ChevronDownIcon=()=><Icon size={16}><path d="m6 9 6 6 6-6"/></Icon>;
export const ChevronLeftIcon=()=><Icon size={16}><path d="m15 6-6 6 6 6"/></Icon>;
export const ChevronRightIcon=()=><Icon size={16}><path d="m9 6 6 6-6 6"/></Icon>;
export const CallsIcon=()=><Icon><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/>
  <path d="m8.2 10.8 7.6-3.6M8.2 13.2l7.6 3.6"/></Icon>;
export const ChainIcon=()=><Icon><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></Icon>;
export const StackIcon=()=><Icon><rect x="3.5" y="4" width="17" height="4.5" rx="1.5"/><rect x="3.5" y="10" width="17" height="4.5" rx="1.5"/>
  <rect x="3.5" y="16" width="17" height="4" rx="1.5"/></Icon>;
export const ListIcon=()=><Icon><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor"/>
  <circle cx="4.5" cy="12" r="1" fill="currentColor"/><circle cx="4.5" cy="18" r="1" fill="currentColor"/></Icon>;
export const PlusIcon=()=><Icon size={20}><path d="M12 5v14M5 12h14"/></Icon>;
export const MinusIcon=()=><Icon size={20}><path d="M5 12h14"/></Icon>;
export const FitIcon=()=><Icon size={20}><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/></Icon>;
export const LocateIcon=()=><Icon size={20}><circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></Icon>;
export const ExpandIcon=()=><Icon size={20}><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></Icon>;
export const ShrinkIcon=()=><Icon size={20}><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M3 21l7-7"/></Icon>;
export const DownloadIcon=()=><Icon size={20}><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19h14"/></Icon>;
