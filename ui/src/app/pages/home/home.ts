// home.ts - The home page, shown at "/" (see app.routes.ts).
// For now it only says Hello World; later it becomes the "ask a question" page.

import { Component } from '@angular/core';

@Component({
  selector: 'app-home',          // tag name, if this component is ever used inside another template
  templateUrl: './home.html',    // the page's HTML
  styleUrl: './home.css',        // styles that apply to this page only
})
export class Home {
  // Values the template shows. "protected" = usable in home.html, hidden from other code.
  protected readonly heading = 'Hello World';
  protected readonly subtitle = 'Stocks Platform - ask questions about Indian listed companies’ filings.';
}
