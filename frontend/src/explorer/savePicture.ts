// Enregistrer l'image d'un diagramme : le SVG autonome de `picture.ts` rendu dans un canevas, puis téléchargé en PNG.
// Rien ne quitte le navigateur.

/** Le PNG d'un SVG, deux fois plus fin que l'écran, téléchargé sous `name`. */
export async function savePicture(svg:string, width:number, height:number, name:string, scale=2){
  const source=URL.createObjectURL(new Blob([svg], {type:'image/svg+xml;charset=utf-8'}));
  try{
    const image=new Image();
    image.src=source;
    await image.decode();
    const canvas=document.createElement('canvas');
    canvas.width=Math.ceil(width*scale);canvas.height=Math.ceil(height*scale);
    const context=canvas.getContext('2d');
    if(!context)throw new Error('canevas indisponible');
    context.scale(scale, scale);
    context.drawImage(image, 0, 0, width, height);
    const png=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve, 'image/png'));
    if(!png)throw new Error('conversion en PNG impossible');
    const target=URL.createObjectURL(png), link=document.createElement('a');
    link.href=target;link.download=name;
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(target), 1000);
  }finally{
    URL.revokeObjectURL(source);
  }
}

/** Un nom de fichier lisible et sûr. */
export const fileName=(...words:string[])=>`${words.join('-').normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase().slice(0, 80)||'diagramme'}.png`;
