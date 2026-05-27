/** Reset window/document scroll (avoids clipped header after refresh). */
export function resetPageScroll(): void {
  window.scrollTo(0, 0);
  document.documentElement.scrollLeft = 0;
  document.documentElement.scrollTop = 0;
  document.body.scrollLeft = 0;
  document.body.scrollTop = 0;
}
