import { http, HttpResponse} from 'msw'

const summaries = [
  {
    transcript: '1',
    summary_type: 'topic',
    topic: '1',
    text: "The committee discussed the value of placing data centers, powered by solar energy over agricultural land, in Missouri's rural communities.",
  },
  {
    transcript: '1',
    summary_type: 'general',
    topic: null,
    text: 'General summary text...',
  },
]

export const handlers = [
    // http.get('/api/topics/1', () => {
    //     return HttpResponse.json({
    //         id: '1',

    //     })
    // })
    http.get('/api/summaries/', ({ request }) => {
        const url = new URL(request.url);
        const transcriptId = url.searchParams.get('transcript');
        const filtered = transcriptId ? summaries.filter((s) => s.transcript === transcriptId) : summaries

        return HttpResponse.json(filtered)
    })
]