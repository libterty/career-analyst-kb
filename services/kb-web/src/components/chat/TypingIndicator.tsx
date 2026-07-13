export default function TypingIndicator() {
  return (
    <div className="msg-bubble msg-bot shadow-sm flex gap-1 items-center">
      {[0, 0.2, 0.4].map((delay, i) => (
        <span
          key={i}
          className="w-2 h-2 bg-blue-500 rounded-full inline-block"
          style={{ animation: `blink 1.2s ${delay}s infinite` }}
        />
      ))}
      <style jsx>{`
        @keyframes blink {
          0%, 80%, 100% { opacity: 0; }
          40% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
