// Ouvrir l'explorateur sur une référence, depuis une autre page (TAXO-01J § 9) : une route, une règle, un module, un
// commit, un fichier touché. Sans analyse nommée, l'explorateur ouvre l'analyse affichée.
import {href} from '../nav';

export const explorerHref=(root:string, analysis?:string)=>href('explorer', undefined, {racine:root, analyse:analysis});
