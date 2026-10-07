import {describe, expect, it} from 'vitest';
import {chain, type ChainText} from './chain';
import {linksOf, viewOf} from './graph';
import {escape, picture, type Palette} from './picture';
import {fileName} from './savePicture';
import {depthCut, element, tile} from './__fixtures__/tiles';

const ROUTE='endpoint:GET /a?x=1&y=<2>', CONTROLLER='symbol:java:A#get()';
const text:ChainText={name:value=>({owner:value}), note:boundary=>boundary.reason, cut:boundary=>`coupure ${boundary.reason}`,
  revisit:(link, target)=>target, leaf:value=>value??''};
const palette:Palette={surface:'#fff', text:'#111', muted:'#666', line:'#789', frontier:'#c47a12', frontierSoft:'#fdf3e1',
  cut:'#eee', border:'#ccc'};

describe('l’image d’un diagramme', ()=>{
  const view=viewOf(tile({root:ROUTE, items:[element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})],
    nodes:[[ROUTE, 0, true], [CONTROLLER, 1, false]], frontier:[depthCut(CONTROLLER)]}));
  const layout=chain(view, linksOf(view), ()=>'CHAIN', text);
  const svg=picture(layout, palette, box=>({stereo:`«${box.key}»`, tone:'#2f6fd6'}), ()=>({verb:'est traité par', marks:['O']}));

  it('est un SVG autonome, à la taille du dessin', ()=>{
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true);
    expect(svg).toContain(`width="${layout.width}" height="${layout.height}"`);
    expect(svg).not.toMatch(/<foreignObject|<image|https?:\/\/(?!www\.w3\.org)/);
  });

  it('reprend chaque texte de la mise en page, échappé, et chaque étiquette', ()=>{
    expect(svg).toContain(escape(ROUTE));
    expect(svg).not.toContain('<2>');
    expect(svg).toContain('coupure DEPTH');
    expect(svg).toContain('>est traité par</text>');
    expect(svg).toContain('>O</text>');
    expect((svg.match(/marker-end=/g)??[]).length).toBe(layout.arrows.length);
  });

  it('nomme le fichier lisiblement, sans caractère risqué', ()=>{
    expect(fileName('taxo', 'Appels', 'route GET /api/courses')).toBe('taxo-appels-route-get-api-courses.png');
    expect(fileName('taxo', 'Chaîne', '')).toBe('taxo-chaine.png');
  });
});
