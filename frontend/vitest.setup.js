import { beforeAll, afterEach, afterAll } from 'vitest'
import { server } from './src/mocks/node.js'
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react' 

beforeAll(() => {
    if (!window.matchMedia) {
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            value: (query) => ({
                matches: false,
                media: query,
                onchange: null,
                addListener: () => {},
                removeListener: () => {},
                addEventListener: () => {},
                removeEventListener: () => {},
                dispatchEvent: () => false,
            }),
        })
    }
    server.listen()
})
afterEach(() => { 
    server.resetHandlers();
    cleanup();
})
afterAll(() => server.close())
