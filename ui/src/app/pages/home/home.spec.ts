// home.spec.ts - Unit tests for the home page (run with: npm test).

import { TestBed } from '@angular/core/testing';
import { Home } from './home';

describe('Home', () => {
  it('shows Hello World', async () => {
    const fixture = TestBed.createComponent(Home);   // build the page in a fake browser
    await fixture.whenStable();                      // wait until it has rendered
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('h1')?.textContent).toContain('Hello World');
  });
});
