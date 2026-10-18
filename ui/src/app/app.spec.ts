// app.spec.ts - Unit tests for the root component and the routes (run with: npm test).

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { App } from './app';
import { routes } from './app.routes';

describe('App', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('creates the app', () => {
    expect(TestBed.createComponent(App).componentInstance).toBeTruthy();
  });

  it('shows the home page at "/"', async () => {
    const harness = await RouterTestingHarness.create('/');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain('Stocks Platform');
  });

  it('sends unknown URLs to the home page', async () => {
    const harness = await RouterTestingHarness.create('/no-such-page');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain('Stocks Platform');
  });
});
