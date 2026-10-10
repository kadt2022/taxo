import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {ElementView} from './element';

const SERVICE='symbol:java:com.example.demo.service.CourseService#register(String)';
const CONTROLLER='symbol:java:com.example.demo.controller.CourseController#register(String)';

describe('ElementView', ()=>{
  it('ouvre l’explorateur centré sur l’élément reconnu, dans la même analyse', ()=>{
    const html=renderToStaticMarkup(<ElementView located={{status:'FOUND', anchor:SERVICE, candidates:[SERVICE], analysis:'a1'}}/>);
    expect(html).toContain('ÉLÉMENT RECONNU');
    expect(html).toContain('com.example.demo.service.CourseService#register(String)');
    const link=new URLSearchParams(/href="#\/explorer\?([^"]+)"/.exec(html)![1].replaceAll('&amp;', '&'));
    expect(link.get('racine')).toBe(SERVICE);
    expect(link.get('analyse')).toBe('a1');
    expect(html).toContain(`aria-label="Ouvrir dans l’explorateur : ${SERVICE}"`);
  });
  it('laisse le choix entre plusieurs éléments, sans en choisir un', ()=>{
    const html=renderToStaticMarkup(<ElementView located={{status:'AMBIGUOUS', anchor:null, candidates:[CONTROLLER, SERVICE], more_candidates:2}}/>);
    expect(html).toContain('PLUSIEURS ÉLÉMENTS');
    expect(html).toContain('Taxo ne choisit pas à votre place');
    expect(html.match(/class="explore-link"/g)).toHaveLength(2);
    expect(html).toContain('Et 2 autres : précisez le nom.');
    expect(html).not.toContain('ÉLÉMENT RECONNU');
  });
  it('dit quand la recherche n’a pas pu conclure, et quoi nommer quand rien ne l’est', ()=>{
    expect(renderToStaticMarkup(<ElementView located={{status:'AMBIGUOUS', anchor:null, candidates:[]}}/>))
      .toContain('recherche incomplète');
    const none=renderToStaticMarkup(<ElementView located={{status:'NONE', anchor:null, candidates:[]}}/>);
    expect(none).toContain('nommez l’élément');
    expect(none).not.toContain('explore-link');
  });
});
