// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {folderOf, hue, ProjectSwitcher} from './switcher';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

let host:HTMLElement, root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});

const click=(node:Element|null|undefined)=>act(()=>{node?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
const type=(input:HTMLInputElement, value:string)=>act(()=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value);
  input.dispatchEvent(new Event('input', {bubbles:true}));});
const PROJECTS=['Iam', 'Takibo', 'Taxo', 'Uaa', 'keycloak', 'multi-tenant-access-management-platform']
  .map((name, index)=>({id:`p${index}`, name, path:index===5?'D:\\Projets\\mtamp':`D:\\Projets\\${name}\\`}));

function mount(projects=PROJECTS, onAdd=vi.fn(async()=>true)){
  const onOpen=vi.fn();
  act(()=>{root.render(<ProjectSwitcher projects={projects} selected="p0" status="il y a 3 h" busy={false} onOpen={onOpen} onAdd={onAdd}/>);});
  return {onOpen, onAdd};
}
const options=()=>Array.from(host.querySelectorAll('[role="option"]'));

describe('sélecteur de projet', ()=>{
  it('montre le projet actif, fermé, avec l’âge de sa dernière analyse', ()=>{
    mount();
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Iam');
    expect(host.querySelector('.switcher-current small')?.textContent).toBe('il y a 3 h');
    expect(host.querySelector('.switcher-current small')?.getAttribute('title')).toBe('Dernière analyse il y a 3 h');
    expect(host.querySelector('.switcher-current')?.getAttribute('aria-expanded')).toBe('false');
    expect(host.querySelector('.switcher-panel')).toBeNull();
  });

  it('s’ouvre sur tous les projets, l’actif coché, et en ouvre un autre', ()=>{
    const {onOpen}=mount();
    click(host.querySelector('.switcher-current'));
    expect(host.querySelector('.switcher-count')?.textContent).toBe('6');
    expect(options()).toHaveLength(6);
    expect(options()[0].getAttribute('aria-selected')).toBe('true');
    expect(options()[0].querySelector('.switcher-check')).not.toBeNull();
    expect(options()[1].querySelector('small')).toBeNull();
    expect(options()[5].querySelector('small')?.textContent).toBe('mtamp');
    click(options()[0]);
    expect(onOpen).not.toHaveBeenCalled();
    click(host.querySelector('.switcher-current'));
    click(options()[2]);
    expect(onOpen).toHaveBeenCalledWith('p2');
    expect(host.querySelector('.switcher-panel')).toBeNull();
  });

  it('cherche un projet par son nom ou son dossier', ()=>{
    mount();
    click(host.querySelector('.switcher-current'));
    const search=host.querySelector('.switcher-search') as HTMLInputElement;
    type(search, 'KEY');
    expect(options().map(item=>item.querySelector('strong')?.textContent)).toEqual(['keycloak']);
    type(search, 'rien');
    expect(host.querySelector('.switcher-empty')?.textContent).toContain('rien');
  });

  it('ajoute un projet sur place, puis se referme', async()=>{
    const {onAdd}=mount();
    click(host.querySelector('.switcher-current'));
    click(host.querySelector('.switcher-add'));
    const [name, path]=Array.from(host.querySelectorAll('.switcher-form input')) as HTMLInputElement[];
    type(name, 'Nouveau');type(path, 'D:\\Nouveau');
    await act(async()=>{host.querySelector('.switcher-form')?.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));});
    expect(onAdd).toHaveBeenCalledWith('Nouveau', 'D:\\Nouveau');
    expect(host.querySelector('.switcher-panel')).toBeNull();
  });

  it('garde le formulaire quand l’ajout est refusé, et l’annule', async()=>{
    mount(PROJECTS.slice(0, 2), vi.fn(async()=>false));
    click(host.querySelector('.switcher-current'));
    expect(host.querySelector('.switcher-search')).toBeNull();
    click(host.querySelector('.switcher-add'));
    await act(async()=>{host.querySelector('.switcher-form')?.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));});
    expect(host.querySelector('.switcher-form')).not.toBeNull();
    click(Array.from(host.querySelectorAll('.switcher-form button')).find(item=>item.textContent==='Annuler'));
    expect(host.querySelector('.switcher-add')).not.toBeNull();
  });

  it('se referme au clic ailleurs, sur Échap, ou vers la gestion des projets', ()=>{
    mount();
    click(host.querySelector('.switcher-current'));
    act(()=>{document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));});
    expect(host.querySelector('.switcher-panel')).toBeNull();
    click(host.querySelector('.switcher-current'));
    act(()=>{document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));});
    expect(host.querySelector('.switcher-panel')).toBeNull();
    click(host.querySelector('.switcher-current'));
    expect(host.querySelector('.switcher-manage')?.getAttribute('href')).toBe('#/projets');
    click(host.querySelector('.switcher-manage'));
    expect(host.querySelector('.switcher-panel')).toBeNull();
  });

  it('sans projet : propose d’en choisir un', ()=>{
    mount([]);
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Choisir un projet');
    click(host.querySelector('.switcher-current'));
    expect(host.querySelector('.switcher-list')).toBeNull();
    expect(host.querySelector('.switcher-manage')).toBeNull();
  });

  it('une teinte stable par projet, et le dossier en clair', ()=>{
    expect(hue('p1')).toBe(hue('p1'));
    expect(hue('p1')).not.toBe(hue('p2'));
    expect(folderOf('D:\\Projets\\Iam\\')).toBe('Iam');
    expect(folderOf('/home/me/taxo')).toBe('taxo');
    expect(folderOf()).toBe('');
  });
});
