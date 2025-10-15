export function getCsrfToken() {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith('csrftoken='))?.split('=')[1]
}
