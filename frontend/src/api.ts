// Adresse d'un appel a l'API de Taxo. Le portail n'appelle que sa propre API : une adresse construite avec des
// valeurs venues de l'ecran (identifiants, choix d'analyse) est verifiee avant tout appel reseau.
const PREFIX='/api/';

/** URL absolue d'un chemin d'API, toujours sur l'origine du portail ; leve une erreur sinon. */
export function apiUrl(path:string, origin:string=globalThis.location?.origin??'http://localhost'){
  const target=path.startsWith(PREFIX)?path:`/api${path.startsWith('/')?'':'/'}${path}`;
  const url=new URL(target, origin);
  const segments=url.pathname.split('/');
  if(url.origin!==new URL(origin).origin||!url.pathname.startsWith(PREFIX)||segments.includes('..')||segments.includes('.'))
    throw new Error('Adresse d’API refusée.');
  return url;
}
