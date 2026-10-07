// @vitest-environment happy-dom
// Enregistrer l'image : le canevas est simulé, le navigateur de test ne dessinant pas.
import {afterEach, describe, expect, it, vi} from 'vitest';
import {savePicture} from './savePicture';

const SVG='<svg xmlns="http://www.w3.org/2000/svg" width="10" height="5"></svg>';

describe('enregistrer l’image d’un diagramme', ()=>{
  afterEach(()=>{vi.restoreAllMocks();});

  function browser(context:object|null, png:Blob|null=new Blob(['png'], {type:'image/png'})){
    vi.spyOn(HTMLImageElement.prototype, 'decode').mockResolvedValue(undefined);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as never);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback=>callback(png));
    const urls=vi.spyOn(URL, 'createObjectURL').mockReturnValueOnce('blob:svg').mockReturnValueOnce('blob:png');
    const revoked=vi.spyOn(URL, 'revokeObjectURL').mockImplementation(()=>undefined);
    const clicked:HTMLAnchorElement[]=[];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this:HTMLAnchorElement){clicked.push(this);});
    return {urls, revoked, clicked};
  }

  it('dessine le SVG deux fois plus fin, puis télécharge le PNG sous son nom', async()=>{
    const drawn={scale:vi.fn(), drawImage:vi.fn()};
    const {urls, revoked, clicked}=browser(drawn);
    await savePicture(SVG, 10, 5, 'taxo-appels.png');
    expect(urls).toHaveBeenCalledTimes(2);
    expect(drawn.scale).toHaveBeenCalledWith(2, 2);
    expect(drawn.drawImage).toHaveBeenCalledWith(expect.any(HTMLImageElement), 0, 0, 10, 5);
    expect(clicked.map(link=>[link.download, link.href])).toEqual([['taxo-appels.png', 'blob:png']]);
    expect(revoked).toHaveBeenCalledWith('blob:svg');
    expect(document.querySelector('a[download]'), 'le lien temporaire est retiré').toBeNull();
  });

  it('échoue clairement sans canevas ou sans PNG, et libère toujours le SVG', async()=>{
    const first=browser(null);
    await expect(savePicture(SVG, 10, 5, 'a.png')).rejects.toThrow('canevas indisponible');
    expect(first.revoked).toHaveBeenCalledWith('blob:svg');
    vi.restoreAllMocks();
    const second=browser({scale:vi.fn(), drawImage:vi.fn()}, null);
    await expect(savePicture(SVG, 10, 5, 'a.png')).rejects.toThrow('conversion en PNG impossible');
    expect(second.clicked).toEqual([]);
  });
});
