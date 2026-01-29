import { beforeAll, afterEach, afterAll } from 'vitest'
import { server } from './src/mocks/node.js'
import '@testing-library/jest-dom/vitest'
 
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())