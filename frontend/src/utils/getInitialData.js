export function getInitialData(initialPayloadElementId) {
    const el = document.getElementById(initialPayloadElementId)
    return el ? JSON.parse(el.textContent) : {}
}