// app.routes.ts - Which page to show for which URL (single page app: the browser
// never reloads; Angular swaps the page inside <router-outlet>).

import { Routes } from '@angular/router';
import { Home } from './pages/home/home';

export const routes: Routes = [
  { path: '', component: Home, title: 'Stocks Platform' },   // "/" -> home page (title = browser tab)
  { path: '**', redirectTo: '' },                             // any unknown URL -> home page
];
