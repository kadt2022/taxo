import {describe, expect, it} from 'vitest';
import {MAX_SHOWN, kindOf, notSentText, ownerOf, refusalText, tileOf} from './code';
import type {SourcePiece} from './protocol';

const piece=(reference:string, from:number, lines:string[], extra:Partial<SourcePiece>={}):SourcePiece=>({reference, path:'src/A.java',
  line_start:from, line_end:from+lines.length-1, truncated:false, declared:{line_start:from, line_end:from+lines.length-1},
  text:lines.join('\n')+'\n', ...extra});

describe('le code d’un nœud', ()=>{
  it('ne lit que le code d’un symbole : type, méthode ou constructeur ; jamais un champ ni une route', ()=>{
    expect(kindOf('symbol:java:a.A')).toBe('type');
    expect(kindOf('symbol:java:a.A#get(String)')).toBe('method');
    expect(kindOf('symbol:java:a.A#A()')).toBe('method');
    expect(kindOf('symbol:java:a.A#items')).toBe('field');
    expect(kindOf('endpoint:GET /orders')).toBe('none');
    expect(kindOf('file:A.java')).toBe('none');
    expect(ownerOf('symbol:java:a.A#get(String)')).toBe('symbol:java:a.A');
    expect(ownerOf('symbol:java:a.A')).toBe('symbol:java:a.A');
  });

  it('numérote depuis la première ligne de la pièce, et surligne la méthode dans son type', ()=>{
    const type=piece('symbol:java:a.A', 10, ['class A {', '  int x;', '  void get() {', '    run();', '  }', '}']);
    const method=piece('symbol:java:a.A#get()', 12, ['  void get() {', '    run();', '  }']);
    const tile=tileOf(method, type);
    expect(tile.from).toBe('type');
    expect(tile.lines.map(line=>line.number)).toEqual([10, 11, 12, 13, 14, 15]);
    expect(tile.lines.filter(line=>line.selected).map(line=>line.number)).toEqual([12, 13, 14]);
    expect(tile.selected).toBe(true);
  });

  it('montre la méthode seule, surlignée, quand le type ne la contient pas en entier', ()=>{
    const cut=piece('symbol:java:a.A', 10, ['class A {', '  int x;'], {truncated:true});
    const method=piece('symbol:java:a.A#get()', 40, ['  void get() {', '  }']);
    const tile=tileOf(method, cut);
    expect(tile.from, 'le type coupé ne couvre pas la méthode').toBe('method');
    expect(tile.lines.every(line=>line.selected)).toBe(true);
    expect(tile.lines.map(line=>line.number)).toEqual([40, 41]);
    expect(tileOf(method, null).from).toBe('method');
  });

  it('un type seul n’a rien de surligné', ()=>{
    const tile=tileOf(piece('symbol:java:a.A', 1, ['class A {', '}']));
    expect(tile.selected).toBe(false);
    expect(tile.lines.some(line=>line.selected)).toBe(false);
    expect(tile.from).toBe('type');
  });

  it('borne l’affichage à MAX_SHOWN lignes, autour de la méthode choisie, et dit combien il y en a', ()=>{
    const body=Array.from({length:200}, (_, index)=>`  line ${index+1};`);
    const type=piece('symbol:java:a.A', 1, body);
    const method=piece('symbol:java:a.A#m()', 150, body.slice(149, 155));
    const tile=tileOf(method, type);
    expect(tile.lines).toHaveLength(MAX_SHOWN);
    expect(tile.total).toBe(200);
    expect(tile.lines.some(line=>line.number===150&&line.selected), 'la méthode reste dans la fenêtre').toBe(true);
    expect(tile.last).toBeLessThanOrEqual(200);
    expect(tile.first).toBeGreaterThanOrEqual(1);
    const head=tileOf(piece('symbol:java:a.A', 1, body));
    expect(head.first, 'sans sélection, la fenêtre commence en tête').toBe(1);
    expect(head.lines).toHaveLength(MAX_SHOWN);
  });

  it('dit pourquoi Taxo n’a pas transmis le code, et ce qui lève un refus de consentement', ()=>{
    expect(notSentText('CONFIDENTIAL')).toBe('Taxo n’a pas transmis ce code : le fichier est confidentiel.');
    expect(notSentText('INCONNU')).toContain('INCONNU');
    expect(refusalText('NO_CONSENT', 'Non autorisée.')).toContain('TAXO_SOURCE_READING=symbol');
    expect(refusalText('NOT_AVAILABLE', 'Pas de commit.')).toBe('Pas de commit.');
  });
});


describe('la fenêtre de code lève la borne d’affichage', ()=>{
  const body=Array.from({length:200}, (_, index)=>`  line ${index+1};`);
  const type=piece('symbol:java:a.A', 1, body);
  const method=piece('symbol:java:a.A#m()', 150, body.slice(149, 155));

  it('sans limite, toutes les lignes de la pièce sont montrées, la méthode surlignée', ()=>{
    const whole=tileOf(method, type, Number.POSITIVE_INFINITY);
    expect(whole.lines).toHaveLength(200);
    expect([whole.first, whole.last, whole.total]).toEqual([1, 200, 200]);
    expect(whole.lines.filter(line=>line.selected).map(line=>line.number)).toEqual([150, 151, 152, 153, 154, 155]);
  });

  it('avec la limite par défaut, la fenêtre reste bornée autour de la méthode', ()=>{
    expect(tileOf(method, type).lines).toHaveLength(MAX_SHOWN);
    expect(tileOf(method, type, 50).lines).toHaveLength(50);
    expect(tileOf(method, type, 50).lines.some(line=>line.number===150&&line.selected)).toBe(true);
  });
});
