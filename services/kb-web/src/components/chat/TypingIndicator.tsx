export default function TypingIndicator() {
  return (
    <div className="self-start max-w-[80%] px-4 py-3 rounded-2xl bg-white border border-gray-200 shadow-sm flex gap-1.5 items-center">
      {[0, 0.2, 0.4].map((delay, i) => (
        <span
          key={i}
          className="w-2.5 h-2.5 bg-blue-400 rounded-full inline-block"
          style={{ animation: `typing-dot 1.2s ${delay}s infinite` }}
        />
      ))}
    </div>
  );
}
