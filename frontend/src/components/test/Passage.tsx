import DOMPurify from 'dompurify'

interface PassageProps {
  content: string
  source?: string | null
}

export function Passage({ content, source }: PassageProps) {
  const sanitized = DOMPurify.sanitize(content, {
    ALLOWED_TAGS: [
      'p', 'br', 'span', 'div', 'strong', 'em', 'b', 'i', 'u', 's',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li', 'blockquote', 'sup', 'sub',
      'a', 'img', 'hr', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
    ],
    ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'role', 'aria-level', 'colspan', 'rowspan'],
  })

  return (
    <div className="h-full overflow-y-auto pr-2">
      <div
        className="prose prose-sm max-w-none text-gray-800 leading-relaxed"
        dangerouslySetInnerHTML={{ __html: sanitized }}
      />
      {source && (
        <p className="mt-3 text-xs text-gray-400 italic">— {source}</p>
      )}
    </div>
  )
}
