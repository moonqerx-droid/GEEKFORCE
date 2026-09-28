import "./QuickReplies.css";

/** Answers to the assistant's closed question, one tap each; typing stays available below. */
export function QuickReplies({ replies, onPick }: { replies: string[]; onPick: (reply: string) => void }) {
  return (
    <div className="quick-replies" role="group" aria-label="Быстрый ответ">
      {replies.map((reply) => (
        <button key={reply} type="button" className="quick-reply" onClick={() => onPick(reply)}>
          {reply}
        </button>
      ))}
    </div>
  );
}
