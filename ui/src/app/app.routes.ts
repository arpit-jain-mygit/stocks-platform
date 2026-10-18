// app.routes.ts - Which page to show for which URL (single page app: the browser
// never reloads; Angular swaps the page inside <router-outlet>).

import { Routes } from '@angular/router';
import { Home } from './pages/home/home';
import { CompanyPage } from './pages/company/company';

export const routes: Routes = [
  { path: '', component: Home, title: 'Stocks Platform' },                       // "/" -> company cards
  { path: 'companies/:id', component: CompanyPage, title: 'Company - Stocks Platform' },   // one company
  { path: '**', redirectTo: '' },                                                  // unknown URL -> home
];
