import { initChrome } from './chrome.js';
import { initRouter, currentPage } from './router.js';

initRouter();
initChrome(currentPage());
