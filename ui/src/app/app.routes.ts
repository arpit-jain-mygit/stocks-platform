// app.routes.ts - Which view to show for which URL. A single page app: the browser loads
// index.html once and Angular swaps views inside <router-outlet>. Today there is one view;
// company details open inside their card, so the address stays "/".

import { Routes } from '@angular/router';
import { Home } from './pages/home/home';

export const routes: Routes = [
  { path: '', component: Home, title: 'Stocks Platform' },   // "/" -> company cards
  { path: '**', redirectTo: '' },                             // any unknown URL -> home
];
