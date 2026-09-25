import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {ConsultForm, submitConsult, typed} from './consult';
import {MAX_COMMITS} from './history';

describe('submitConsult', ()=>{
  it('consulte le nombre demandé', ()=>{
    const event={preventDefault:vi.fn()}, onConsult=vi.fn(), onError=vi.fn();
    submitConsult(event, '/c', '3', {onConsult, onError});
    expect(event.preventDefault).toHaveBeenCalled();
    expect(onConsult).toHaveBeenCalledWith('/c?limit=3');
    expect(onError).not.toHaveBeenCalled();
  });
  it('ne lit rien sans nombre valable', ()=>{
    const onConsult=vi.fn(), onError=vi.fn();
    submitConsult({preventDefault(){}}, '/c', '', {onConsult, onError});
    expect(onConsult).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(`Indiquez un nombre de commits entre 1 et ${MAX_COMMITS}.`);
  });
});

describe('ConsultForm', ()=>{
  it('demande un nombre explicite, sans valeur par défaut', ()=>{
    const html=renderToStaticMarkup(<ConsultForm base="/c" busy={false} onConsult={()=>{}} onError={()=>{}}/>);
    expect(html).toContain('id="commit-count"');
    expect(html).toContain(`max="${MAX_COMMITS}"`);
    expect(html).toContain('value=""');
    expect(html).toContain('type="submit"');
  });
  it('se désactive pendant une opération', ()=>{
    expect(renderToStaticMarkup(<ConsultForm base="/c" busy onConsult={()=>{}} onError={()=>{}}/>)).toContain('disabled=""');
  });
});

describe('typed', ()=>{
  it('transmet la saisie brute', ()=>{
    const set=vi.fn();
    typed(set)({target:{value:'12'}});
    expect(set).toHaveBeenCalledWith('12');
  });
});
