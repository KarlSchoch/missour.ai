import { http, HttpResponse} from 'msw'
import summaries from '@fixtures/api/summary/list.json'
import topics from '@fixtures/api/topic/list.json'

export const handlers = [
    http.get('/api/summaries/', ({ request }) => {
        const url = new URL(request.url);
        const transcriptId = url.searchParams.get('transcript');
        const filtered = transcriptId
            ? summaries.filter((s) => String(s.transcript) === transcriptId)
            : summaries

        return HttpResponse.json(filtered)
    }),
    http.get('/api/topics/', ({ request }) => {
      return HttpResponse.json(topics)
    })
]
