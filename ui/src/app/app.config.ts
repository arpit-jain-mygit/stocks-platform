// app.config.ts - App-wide services, set up once when the app starts.

import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),  // report uncaught errors in the console
    provideRouter(routes),                 // URL -> page (app.routes.ts)
    provideHttpClient(withFetch()),        // HttpClient for calling the backend (services/stocks-api.ts)
  ],
};
