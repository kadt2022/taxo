import {describe, expect, it} from 'vitest';
import {highlight, languageOf, type Kind} from './highlight';

/** Les éléments d'une ligne sous la forme `texte:sorte`, pour lire un résultat d'un coup d'œil. */
const flat=(line:string, before:string[]=[])=>{
  const lines=highlight([...before, line], 'java');
  return lines[lines.length-1].map(token=>`${token.text}:${token.kind}`);
};
const kinds=(line:string)=>new Set<Kind>(highlight([line], 'java')[0].map(token=>token.kind));

describe('la coloration du code', ()=>{
  it('ne colore que ce qu’elle sait lire : Java par l’extension du fichier', ()=>{
    expect(languageOf('src/A.java')).toBe('java');
    expect(languageOf('src/a.JAVA')).toBe('java');
    expect(languageOf('src/a.py')).toBe('');
    expect(highlight(['def f(): return 1', ''], '')).toEqual([[{text:'def f(): return 1', kind:'plain'}], []]);
  });

  it('distingue annotation, mot-clé, type, appel et texte courant dans une déclaration', ()=>{
    expect(flat('@GetMapping("/admin/users")')).toEqual(['@GetMapping:annotation', '(:plain', '"/admin/users":string', '):plain']);
    expect(flat('    public String get() {')).toEqual(['    :plain', 'public:keyword', ' :plain', 'String:type', ' :plain', 'get:method', '() {:plain']);
  });

  it('colore nombres, constantes, littéraux, chaînes avec échappement et apostrophes', ()=>{
    expect(flat('int x = 0x1F + 42L + 3.5e2;')).toContain('0x1F:number');
    expect(flat('int x = 0x1F + 42L + 3.5e2;')).toContain('42L:number');
    expect(flat('int x = 0x1F + 42L + 3.5e2;')).toContain('3.5e2:number');
    expect(flat('return MAX_SIZE == null;')).toEqual(expect.arrayContaining(['return:keyword', 'MAX_SIZE:constant', 'null:keyword']));
    expect(flat('String s = "a\\"b" + \'c\';')).toEqual(expect.arrayContaining(['"a\\"b":string', '\'c\':string']));
    expect(kinds('x = "ouverte').has('string'), 'une chaîne non fermée s’arrête à la fin de la ligne').toBe(true);
  });

  it('colore les commentaires de ligne, de bloc et de bloc ouvert plus haut', ()=>{
    expect(flat('x = 1; // fin')).toEqual(expect.arrayContaining(['// fin:comment']));
    expect(flat('/* a */ int y;')).toEqual(expect.arrayContaining(['/* a */:comment', 'int:keyword']));
    const lines=highlight(['/**', ' * Javadoc avec "guillemets"', ' */', 'class A {}'], 'java');
    expect(lines[0].map(token=>token.kind)).toEqual(['comment']);
    expect(lines[1].map(token=>token.kind), 'le commentaire se poursuit sur la ligne suivante').toEqual(['comment']);
    expect(lines[2].map(token=>token.kind)).toEqual(['comment']);
    expect(lines[3].map(token=>token.kind)).toEqual(['keyword', 'plain', 'type', 'plain']);
    expect(flat('  */ int z;', ['/*'])).toEqual(expect.arrayContaining(['int:keyword']));
  });

  it('suit un bloc de texte sur plusieurs lignes', ()=>{
    const lines=highlight(['String t = """', '  select "x"', '  """;', 'int n;'], 'java');
    expect(lines[1].map(token=>token.kind)).toEqual(['string']);
    expect(lines[2].map(token=>token.kind)).toEqual(['string', 'plain']);
    expect(lines[3].map(token=>token.kind)).toContain('keyword');
  });

  it('garde le texte intact : recoller les éléments redonne la ligne', ()=>{
    const source=['@Service', 'public class CourseAccessControlService {', '    private static final int LIMIT = 10; // max',
      '    return courses.stream().filter(course -> course.id() > 0).toList();'];
    highlight(source, 'java').forEach((line, index)=>expect(line.map(token=>token.text).join('')).toBe(source[index]));
  });
});
