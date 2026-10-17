// Le zoom du graphe : une mise à l'échelle du dessin déjà calculé, jamais un nouveau calcul. Pur : des nombres.

/** Les bornes du zoom manuel (boutons + et −) et son pas. */
export const ZOOM_MIN=0.4, ZOOM_MAX=2, ZOOM_STEP=1.25;
/** L'ajustement à la largeur a son propre plancher, bien plus bas : un dessin très large doit tenir, quel que soit le zoom manuel. */
export const FIT_MIN=0.05;

export const zoomIn=(zoom:number)=>Math.min(ZOOM_MAX, zoom*ZOOM_STEP);
export const zoomOut=(zoom:number)=>Math.max(ZOOM_MIN, zoom/ZOOM_STEP);

/** L'échelle qui fait tenir un dessin de `drawn` pixels dans `width` pixels : jamais au-delà de l'échelle naturelle. */
export const fitScale=(width:number, drawn:number)=>Math.max(FIT_MIN, Math.min(1, (width-2)/drawn));
