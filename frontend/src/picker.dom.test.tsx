// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ComparePicker, type Choice} from './picker';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

let host:HTMLElement, root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});

const flush=()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve, 0));});
const click=(node:Element|null|undefined)=>act(()=>{node?.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
const column=(letter:string)=>host.querySelector(`[aria-label="Analyse ${letter}"]`) as HTMLElement;
const items=(letter:string)=>Array.from(column(letter).querySelectorAll('.choice-list button')) as HTMLButtonElement[];
const button=(text:string)=>Array.from(host.querySelectorAll('button')).find(item=>item.textContent?.includes(text));
async function type(input:HTMLInputElement|HTMLSelectElement, value:string){
  await act(async()=>{
    const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event(input instanceof HTMLSelectElement?'change':'input', {bubbles:true}));
  });
}

const commit=(sha:string, subject:string, author:string)=>({sha:sha.repeat(40), subject, author, authored_at:'2026-09-30T12:00:00+00:00'});
const CHOICES:Choice[]=[
  {id:'n3', created_at:'2026-10-01T21:15:00', snapshot:{commit:'a'.repeat(40), mode:'COMMIT'}, commit:commit('a', 'Improve comparison UX', 'Claude'), fact_count:10, failed:[]},
  {id:'n2', created_at:'2026-10-01T19:02:00', snapshot:{commit:'a'.repeat(40), mode:'COMMIT'}, commit:commit('a', 'Improve comparison UX', 'Claude'), fact_count:10, failed:[]},
  {id:'n1', created_at:'2026-09-30T03:22:00', snapshot:{commit:'d'.repeat(40), mode:'COMMIT'}, commit:commit('d', 'Bounded neighborhood', 'Pi'), fact_count:9, failed:[]}];

async function open(choices:Choice[]|Error, initial?:{before?:string; after?:string}){
  const onCompare=vi.fn(), onClose=vi.fn();
  const request=vi.fn(()=>choices instanceof Error?Promise.reject(choices):Promise.resolve(choices)) as unknown as <T>(path:string)=>Promise<T>;
  await act(async()=>{root.render(<ComparePicker base="/projects/p" request={request} initial={initial} onCompare={onCompare} onClose={onClose}/>);});
  await flush();
  return {onCompare, onClose, request};
}

describe('comparateur de deux analyses', ()=>{
  it('choisit A puis B, refuse la même analyse des deux côtés, puis compare dans ce sens', async()=>{
    const {onCompare, request}=await open(CHOICES);
    expect(request).toHaveBeenCalledWith('/projects/p/comparisons/analyses');
    expect((button('Comparer →') as HTMLButtonElement).disabled).toBe(true);
    await click(items('A')[2]);
    expect(column('A').textContent).toContain('Bounded neighborhood');
    expect(items('B')[2].disabled).toBe(true);
    expect(items('B')[2].textContent).toContain('déjà choisie en A');
    await click(items('B')[0]);
    await click(button('Comparer →'));
    expect(onCompare).toHaveBeenCalledWith('n1', 'n3');
  });

  it('signale deux analyses du même commit avant de comparer', async()=>{
    await open(CHOICES, {before:'n2', after:'n3'});
    expect(host.textContent).toContain('Deux analyses du même commit');
  });

  it('recherche par auteur, puis par date de l’analyse', async()=>{
    await open(CHOICES);
    const [field]=Array.from(column('A').querySelectorAll('select'));
    await type(field, 'author');
    await type(column('A').querySelector('input[type="search"]') as HTMLInputElement, 'pi');
    expect(items('A').map(item=>item.textContent)).toEqual([expect.stringContaining('Bounded neighborhood')]);
    expect(column('A').textContent).toContain('1 analyse sur 3');
    await type(column('A').querySelector('input[type="search"]') as HTMLInputElement, 'personne');
    expect(column('A').textContent).toContain('Aucune analyse ne répond');
    const [from]=Array.from(column('B').querySelectorAll('input[type="date"]')) as HTMLInputElement[];
    await type(from, '2026-10-01');
    expect(items('B')).toHaveLength(2);
  });

  it('garde A fixée (« Comparer avec… ») et permet d’en choisir une autre', async()=>{
    await open(CHOICES, {before:'n2'});
    expect(column('A').querySelector('.choice-list')).toBeNull();
    expect(column('A').textContent).toContain('Improve comparison UX');
    await click(Array.from(column('A').querySelectorAll('button')).find(item=>item.textContent?.includes('Choisir une autre analyse')));
    expect(items('A')).toHaveLength(3);
  });

  it('dit qu’il faut deux analyses, ou l’erreur de l’API, et rend la main', async()=>{
    const {onClose}=await open(CHOICES.slice(0, 1));
    expect(host.textContent).toContain('Une seule analyse complète');
    await click(button('Vue d’ensemble'));
    expect(onClose).toHaveBeenCalledOnce();
    act(()=>root.unmount());root=createRoot(host);
    await open(new Error('Projet introuvable.'));
    expect(host.querySelector('[role="alert"]')?.textContent).toBe('Projet introuvable.');
  });

  it('affiche plus d’analyses sur demande', async()=>{
    const many=Array.from({length:35}, (_, index):Choice=>({...CHOICES[2], id:`m${index}`}));
    await open(many);
    expect(items('A')).toHaveLength(30);
    await click(Array.from(column('A').querySelectorAll('button')).find(item=>item.textContent==='Afficher plus'));
    expect(items('A')).toHaveLength(35);
  });
});
