// Consultation de l'historique Git (TAXO-EVAL-01) : toujours explicite, jamais une fenetre par defaut.
export const MAX_COMMITS=100;

/** Nombre de commits demande par l'utilisateur ; null si la saisie n'est pas un entier entre 1 et MAX_COMMITS. */
export function commitCount(value:string):number|null{
  const text=value.trim();
  if(!/^\d+$/.test(text))return null;
  const count=Number(text);
  return count>=1&&count<=MAX_COMMITS?count:null;
}
