// app.ts - The root component: the frame every page is shown in.
// It holds only <router-outlet>, where the router puts the current page.

import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  imports: [RouterOutlet],     // components / directives the template uses
  selector: 'app-root',        // matches <app-root> in src/index.html
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {}
