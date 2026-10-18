// app.config.ts - App-wide services, set up once when the app starts.

import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),  // report uncaught errors in the console
    // URL -> page (app.routes.ts). withComponentInputBinding: a URL part like :id
    // arrives in the page as an input, e.g. /companies/OFSS -> id = "OFSS".
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch()),        // HttpClient for calling the backend (services/stocks-api.ts)
  ],
};
