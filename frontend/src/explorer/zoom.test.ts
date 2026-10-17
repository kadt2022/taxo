import {describe, expect, it} from 'vitest';
import {FIT_MIN, ZOOM_MAX, ZOOM_MIN, fitScale, zoomIn, zoomOut} from './zoom';

describe('le zoom du graphe', ()=>{
  it('est borné pour le zoom manuel', ()=>{
    expect(zoomIn(1)).toBe(1.25);
    expect(zoomIn(ZOOM_MAX)).toBe(ZOOM_MAX);
    expect(zoomOut(1)).toBe(0.8);
    expect(zoomOut(ZOOM_MIN)).toBe(ZOOM_MIN);
  });

  it('ajuste à la largeur sans jamais agrandir', ()=>{
    expect(fitScale(1002, 3000)).toBeCloseTo(1000/3000, 5);
    expect(fitScale(5002, 1000), 'un dessin étroit garde son échelle naturelle').toBe(1);
  });

  it('ajuste un dessin très large même sous le plancher du zoom manuel', ()=>{
    const scale=fitScale(402, 2000);
    expect(scale, 'tient dans la largeur').toBeCloseTo(0.2, 5);
    expect(scale, 'sous le plancher du zoom manuel').toBeLessThan(ZOOM_MIN);
    expect(fitScale(2, 1_000_000), 'jamais nul ni négatif').toBe(FIT_MIN);
  });
});
