// app.spec.ts - Unit tests for the root component and the routes (run with: npm test).

import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { RouterTestingHarness } from '@angular/router/testing';
import { App } from './app';
import { appConfig } from './app.config';

describe('App', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      // The app's real setup (router + its options, HttpClient), with a fake backend on top.
      providers: [...appConfig.providers, provideHttpClientTesting()],
    });
  });

  it('creates the app', () => {
    expect(TestBed.createComponent(App).componentInstance).toBeTruthy();
  });

  it('shows the home page at "/"', async () => {
    const harness = await RouterTestingHarness.create('/');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain('stocks-insights.ai');
  });

  it('sends unknown URLs (including old /companies/<code> links) to the home page', async () => {
    const harness = await RouterTestingHarness.create('/companies/OFSS');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain('stocks-insights.ai');
  });
});
