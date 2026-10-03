// Le nommage des références dans l'explorateur : le dépôt par le nom de son projet, le reste par le vocabulaire.
import {createContext, useContext} from 'react';
import {nodeName, type Naming} from './sentences';

export const NamingContext=createContext<Naming>(nodeName);
export const useNaming=()=>useContext(NamingContext);
